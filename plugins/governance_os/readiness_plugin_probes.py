"""Plugin and auxiliary-task readiness probes for Governance OS."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .registry import GovernanceRegistry


REQUIRED_HOOKS = frozenset(
    {
        "pre_gateway_dispatch",
        "pre_tool_call",
        "transform_tool_result",
        "transform_llm_output",
    }
)
REQUIRED_AUXILIARY_TASKS = frozenset(
    {
        "miho_governance_dispatcher",
        "miho_governance_reviewer",
        "miho_governance_promotion_judge",
    }
)
HOOK_CALLBACK_MODULES = {
    "pre_gateway_dispatch": "governance_os.dispatcher",
    "pre_tool_call": "governance_os.guard",
    "transform_tool_result": "governance_os.result_transform",
    "transform_llm_output": "governance_os.delivery_gate",
}


def hook_probe_passed() -> bool:
    from plugins import governance_os

    ctx = _HookProbeContext()
    governance_os.register(ctx)
    registered_hooks = {hook for hook, callback in ctx.hooks if callable(callback)}
    registered_tasks = {str(task.get("key") or "") for task in ctx.tasks}
    return REQUIRED_HOOKS <= registered_hooks and REQUIRED_AUXILIARY_TASKS <= registered_tasks


def manifest_probe_passed() -> bool:
    try:
        import yaml
    except ImportError:
        return False

    try:
        manifest_text = Path(__file__).with_name("plugin.yaml").read_text(encoding="utf-8")
        raw = yaml.safe_load(manifest_text)
    except (OSError, AttributeError, TypeError, yaml.YAMLError):
        return False
    if not isinstance(raw, dict):
        return False
    declared_hooks = _declared_set(raw.get("provides_hooks"))
    declared_tasks = _declared_set(raw.get("provides_auxiliary_tasks"))
    return REQUIRED_HOOKS <= declared_hooks and REQUIRED_AUXILIARY_TASKS <= declared_tasks


def plugin_load_probe_passed() -> bool:
    try:
        from miho_cli.plugins import get_plugin_manager

        manager = get_plugin_manager()
        manager.discover_and_load()
        loaded = manager._plugins.get("governance_os")
    except Exception:
        return False
    if loaded is None or not loaded.enabled or loaded.error:
        return False
    loaded_tasks = set(manager._aux_tasks)
    if not REQUIRED_AUXILIARY_TASKS <= loaded_tasks:
        return False
    return all(
        _has_governance_callback(manager._hooks.get(hook, ()), module)
        for hook, module in HOOK_CALLBACK_MODULES.items()
    )


def auxiliary_instruction_probe_passed() -> bool:
    from plugins import governance_os

    ctx = _HookProbeContext()
    governance_os.register(ctx)
    tasks = {str(task.get("key") or ""): task for task in ctx.tasks}
    return (
        _instruction_has(
            tasks,
            governance_os.DISPATCHER_TASK,
            ("playbook", "required_tools", "missing_context"),
        )
        and _instruction_has(
            tasks,
            governance_os.REVIEWER_TASK,
            ("후검증", "retry_tools", "media_tag"),
        )
        and _instruction_has(
            tasks,
            governance_os.PROMOTION_JUDGE_TASK,
            ("반복 실패", "tests_required", "rollback"),
        )
    )


def auxiliary_dispatcher_dataplane_probe_passed(registry: GovernanceRegistry) -> bool:
    from .dispatcher import (
        _call_auxiliary_dispatcher,
        _needs_auxiliary_dispatch,
        _score_candidates,
        dispatch_request,
    )

    text = "수시 점수 계산 파일 첨부해서 보내줘"
    blob = " ".join(text.casefold().split())
    decision = dispatch_request(registry, text)
    candidates = _score_candidates(registry, blob)
    if not (callable(_call_auxiliary_dispatcher) and bool(candidates)):
        return False
    if not _needs_auxiliary_dispatch(decision, candidates):
        return False

    calls: list[dict[str, object]] = []

    async def fake_async_call_llm(**kwargs: object) -> str:
        calls.append(kwargs)
        return json.dumps(
            {
                "playbook_key": "discord_attachment_delivery",
                "confidence": 0.9,
                "reason": "readiness probe",
            },
            ensure_ascii=False,
        )

    try:
        payload = asyncio.run(
            _call_auxiliary_dispatcher(
                task="miho_governance_dispatcher",
                user_text=text,
                deterministic_decision=decision,
                candidates=candidates,
                call_llm=fake_async_call_llm,
                extract_content=lambda value: value,
            )
        )
    except Exception:
        return False
    return (
        bool(calls)
        and calls[0].get("task") == "miho_governance_dispatcher"
        and payload.get("playbook_key") == "discord_attachment_delivery"
    )


def auxiliary_reviewer_dataplane_probe_passed(registry: GovernanceRegistry) -> bool:
    from .review import (
        _call_auxiliary_reviewer,
        _outcome_from_auxiliary_review,
        _semantic_review_required,
    )

    payload = {
        "student_record_score": 947.3,
        "reviewer": {
            "name": "academy_result_reviewer",
            "status": "pass",
            "checked": ["필수 산출 필드", "상태값"],
        },
    }
    reviewer = payload["reviewer"]
    if not callable(_call_auxiliary_reviewer):
        return False
    calls: list[dict[str, object]] = []

    def fake_call_llm(**kwargs: object) -> str:
        calls.append(kwargs)
        return json.dumps(
            {
                "status": "pass",
                "checked": ["필수 산출 필드", "상태값"],
            },
            ensure_ascii=False,
        )

    try:
        result = _call_auxiliary_reviewer(
            task="miho_governance_reviewer",
            playbook_key="susi_score_calculation",
            tool_name="susi27_score_calculate",
            payload=payload,
            gate_names=("academy_result_reviewer",),
            checked=("필수 산출 필드", "상태값"),
            call_llm=fake_call_llm,
            extract_content=lambda value: value,
        )
    except Exception:
        return False
    outcome = _outcome_from_auxiliary_review(
        result,
        gate_names=("academy_result_reviewer",),
        checked=("필수 산출 필드", "상태값"),
        retry_tools=registry.get_playbook("susi_score_calculation").required_tools,
    )
    return (
        bool(calls)
        and calls[0].get("task") == "miho_governance_reviewer"
        and _semantic_review_required({"semantic_review_required": True}, reviewer)
        and outcome.status == "pass"
        and outcome.reason == "auxiliary_reviewer_pass"
    )


def _declared_set(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def _instruction_has(
    tasks: dict[str, dict[str, object]],
    task_key: str,
    required_terms: tuple[str, ...],
) -> bool:
    task = tasks.get(task_key)
    if not isinstance(task, dict):
        return False
    defaults = task.get("defaults")
    if not isinstance(defaults, dict):
        return False
    instructions = str(defaults.get("instructions") or "")
    return all(term in instructions for term in required_terms)


def _has_governance_callback(callbacks: object, module_fragment: str) -> bool:
    if not isinstance(callbacks, (list, tuple)):
        return False
    for callback in callbacks:
        module_name = str(getattr(callback, "__module__", ""))
        if callable(callback) and module_fragment in module_name:
            return True
    return False


class _HookProbeContext:
    def __init__(self) -> None:
        self.hooks: list[tuple[str, object]] = []
        self.tasks: list[dict[str, object]] = []

    def register_hook(self, hook_name: str, callback: object) -> None:
        self.hooks.append((hook_name, callback))

    def register_auxiliary_task(self, **kwargs: object) -> None:
        self.tasks.append(dict(kwargs))
