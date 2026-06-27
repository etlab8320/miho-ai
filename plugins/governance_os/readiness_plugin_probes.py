"""Plugin and auxiliary-task readiness probes for Governance OS."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any, cast

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
        "miho_governance_reviewer_academy",
        "miho_governance_reviewer_delivery",
        "miho_governance_reviewer_dev",
        "miho_governance_reviewer_research",
        "miho_governance_promotion_judge",
        "miho_self_harness_weakness_miner",
        "miho_self_harness_proposer",
        "miho_governance_final_delivery",
        "miho_governance_final_delivery_orchestrator",
        "miho_governance_semantic_delivery_judge",
        "miho_governance_adversarial_validator",
        "miho_governance_final_qa",
        "miho_governance_final_qa_repair",
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
        manager.discover_and_load(force=True)
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
            ("후검증", "opened artifact inspection", "retry_tools", "media_tag"),
        )
        and _instruction_has(
            tasks,
            governance_os.ACADEMY_REVIEWER_TASK,
            ("학원", "입시", "의미 검수"),
        )
        and _instruction_has(
            tasks,
            governance_os.DELIVERY_REVIEWER_TASK,
            ("첨부", "safe staging path", "MEDIA tag"),
        )
        and _instruction_has(
            tasks,
            governance_os.DEV_REVIEWER_TASK,
            ("개발", "rollback", "배포 안전성"),
        )
        and _instruction_has(
            tasks,
            governance_os.RESEARCH_REVIEWER_TASK,
            ("리서치", "출처", "최신성"),
        )
        and _instruction_has(
            tasks,
            governance_os.PROMOTION_JUDGE_TASK,
            ("반복 실패", "tests_required", "rollback"),
        )
        and _instruction_has(
            tasks,
            governance_os.SELF_HARNESS_WEAKNESS_MINER_TASK,
            ("Weakness Mining", "active registry", "target_surface_hint"),
        )
        and _instruction_has(
            tasks,
            governance_os.SELF_HARNESS_PROPOSER_TASK,
            ("shadow_candidate", "held-out", "기존 미호 동작", "activation", "regression"),
        )
        and _instruction_has(
            tasks,
            governance_os.FINAL_DELIVERY_TASK,
            ("Final Delivery Agent", "deliver/revise/block", "Python guard", "적대적 리뷰"),
        )
        and _instruction_has(
            tasks,
            governance_os.FINAL_DELIVERY_ORCHESTRATOR_TASK,
            ("Final Delivery Orchestrator", "allowed_tools", "tool_contracts", "steps"),
        )
        and _instruction_has(
            tasks,
            governance_os.SEMANTIC_DELIVERY_JUDGE_TASK,
            ("Python feature", "참고 신호", "최종 의미판단", "비결과 답변", "물리적 안전"),
        )
        and _instruction_has(
            tasks,
            governance_os.ADVERSARIAL_VALIDATOR_TASK,
            ("독립", "test receipts", "artifact smoke", "findings=[]"),
        )
        and _instruction_has(
            tasks,
            governance_os.FINAL_QA_TASK,
            ("사용자 질문", "최종 답변 후보", "revise"),
        )
        and _instruction_has(
            tasks,
            governance_os.FINAL_QA_REPAIR_TASK,
            ("새 최종 답변", "Final QA agent", "한국어 평문", "retry_tools"),
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
    from .review_evidence import build_review_evidence
    from .review import (
        _call_auxiliary_reviewer,
        _outcome_from_auxiliary_review,
        _semantic_review_required,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        html_path = Path(temp_dir) / "review.html"
        html_path.write_text("<html><body>서연 수시 점수 947.3</body></html>", encoding="utf-8")
        payload = {
            "student_record_score": 947.3,
            "html_path": str(html_path),
            "reviewer": {
                "name": "academy_result_reviewer",
                "status": "pass",
                "checked": ["필수 산출 필드", "상태값"],
            },
        }
        evidence_bundle = build_review_evidence(payload)
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
            task="miho_governance_reviewer_academy",
            playbook_key="susi_score_calculation",
            tool_name="susi27_score_calculate",
            payload=payload,
            evidence_bundle=evidence_bundle,
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
        and calls[0].get("task") == "miho_governance_reviewer_academy"
        and _probe_has_artifact_inspection(calls[0])
        and _semantic_review_required({"semantic_review_required": True}, reviewer)
        and outcome.status == "pass"
        and outcome.reason == "auxiliary_reviewer_pass"
    )


def _probe_has_artifact_inspection(call: dict[str, object]) -> bool:
    messages = call.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        return False
    message = messages[1]
    if not isinstance(message, dict):
        return False
    try:
        payload = json.loads(str(message.get("content") or ""))
    except json.JSONDecodeError:
        return False
    evidence = payload.get("evidence_bundle")
    if not isinstance(evidence, dict):
        return False
    inspections = evidence.get("artifact_inspections")
    if not isinstance(inspections, dict) or not inspections:
        return False
    return any(
        isinstance(item, dict) and item.get("kind") == "html" and item.get("opened") is True
        for item in inspections.values()
    )


def semantic_delivery_judge_dataplane_probe_passed(registry: GovernanceRegistry) -> bool:
    del registry
    from .semantic_delivery_judge import (
        SEMANTIC_DELIVERY_JUDGE_TASK,
        judge_delivery_semantics,
    )

    calls: list[dict[str, object]] = []

    def fake_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        if "확인한 뒤" in str(kwargs.get("messages") or ""):
            return {
                "content": json.dumps(
                    {
                        "action": "block",
                        "reason": "non_result_deferral",
                        "playbook_key": "academy_hakjong_report",
                        "retry_tools": ["academy_hakjong_report_package"],
                    },
                    ensure_ascii=False,
                )
            }
        return {
            "content": json.dumps(
                {
                    "action": "allow",
                    "reason": "readiness_governance_review_quote",
                    "playbook_key": "",
                    "retry_tools": [],
                },
                ensure_ascii=False,
            )
        }

    verdict = judge_delivery_semantics(
        question="미호 Governance OS 적대적 리뷰해줘",
        answer=(
            "적대적 리뷰 예시: '서연이 수시 환산점수는 947.3점입니다'는 "
            "검증 없이 나가면 안 되는 문장이다."
        ),
        evidence={
            "decision": {"action": "block", "reason": "review_evidence_missing"},
            "python_semantic_decision_is_advisory": True,
        },
        call_llm=fake_call_llm,
        extract_content=_extract_probe_content,
    )
    deferral_verdict = judge_delivery_semantics(
        question="동하 대전대 학종 리포트 PDF로 줘",
        answer="확인한 뒤 PDF로 전달하겠습니다.",
        evidence={
            "decision": {"action": "block", "reason": "non_result_deferral"},
            "python_semantic_decision_is_advisory": True,
        },
        call_llm=fake_call_llm,
        extract_content=_extract_probe_content,
    )
    return (
        len(calls) == 2
        and calls[0].get("task") == SEMANTIC_DELIVERY_JUDGE_TASK
        and calls[1].get("task") == SEMANTIC_DELIVERY_JUDGE_TASK
        and verdict is not None
        and verdict.action == "allow"
        and deferral_verdict is not None
        and deferral_verdict.action == "block"
        and deferral_verdict.retry_tools == ("academy_hakjong_report_package",)
    )


def _extract_probe_content(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("content") or "")
    return str(value or "")


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
    typed_defaults = cast("dict[str, object]", defaults)
    instructions = str(typed_defaults.get("instructions") or "")
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
