"""Plugin registration contract tests for Governance OS."""

from __future__ import annotations

from typing import Any

from plugins import governance_os


class _Ctx:
    def __init__(self) -> None:
        self.tasks: list[dict[str, Any]] = []
        self.hooks: list[str] = []
        self.cli_commands: list[dict[str, Any]] = []

    def register_auxiliary_task(self, key: str, **kwargs: Any) -> None:
        self.tasks.append({"key": key, **kwargs})

    def register_hook(self, hook_name: str, callback: Any) -> None:
        del callback
        self.hooks.append(hook_name)

    def register_cli_command(self, **kwargs: Any) -> None:
        self.cli_commands.append(kwargs)


def test_governance_plugin_registers_auxiliary_judge_tasks() -> None:
    ctx = _Ctx()

    governance_os.register(ctx)

    keys = {task["key"] for task in ctx.tasks}
    assert {
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
        "miho_governance_blocked_delivery_recovery",
        "miho_governance_final_qa",
        "miho_governance_final_qa_repair",
    }.issubset(keys)
    assert "pre_gateway_dispatch" in ctx.hooks
    assert "pre_tool_call" in ctx.hooks
    assert "transform_tool_result" in ctx.hooks
    assert "transform_llm_output" in ctx.hooks
    assert any(command["name"] == "governance" for command in ctx.cli_commands)


def test_governance_auxiliary_tasks_include_operational_instructions() -> None:
    ctx = _Ctx()

    governance_os.register(ctx)

    tasks = {task["key"]: task for task in ctx.tasks}
    dispatcher = tasks["miho_governance_dispatcher"]["defaults"]["instructions"]
    reviewer = tasks["miho_governance_reviewer"]["defaults"]["instructions"]
    academy_reviewer = tasks["miho_governance_reviewer_academy"]["defaults"]["instructions"]
    delivery_reviewer = tasks["miho_governance_reviewer_delivery"]["defaults"]["instructions"]
    promotion = tasks["miho_governance_promotion_judge"]["defaults"]["instructions"]
    weakness_miner = tasks["miho_self_harness_weakness_miner"]["defaults"]["instructions"]
    self_harness_proposer = tasks["miho_self_harness_proposer"]["defaults"]["instructions"]
    final_delivery = tasks["miho_governance_final_delivery"]["defaults"]["instructions"]
    final_delivery_orchestrator = tasks["miho_governance_final_delivery_orchestrator"][
        "defaults"
    ]["instructions"]
    semantic_judge = tasks["miho_governance_semantic_delivery_judge"]["defaults"][
        "instructions"
    ]
    blocked_recovery = tasks["miho_governance_blocked_delivery_recovery"]["defaults"]["instructions"]
    final_qa = tasks["miho_governance_final_qa"]["defaults"]["instructions"]
    final_qa_repair = tasks["miho_governance_final_qa_repair"]["defaults"]["instructions"]

    assert "playbook" in dispatcher
    assert "required_tools" in dispatcher
    assert "후검증" in reviewer
    assert "retry_tools" in reviewer
    assert "입시" in academy_reviewer
    assert "MEDIA tag" in delivery_reviewer
    assert "반복 실패" in promotion
    assert "rollback" in promotion
    assert "Weakness Mining" in weakness_miner
    assert "active registry" in weakness_miner
    assert "shadow_candidate" in self_harness_proposer
    assert "held-out" in self_harness_proposer
    assert "기존 미호 동작" in self_harness_proposer
    assert "activation" in self_harness_proposer
    assert "regression" in self_harness_proposer
    assert "Final Delivery Agent" in final_delivery
    assert "deterministic guard" in final_delivery
    assert "Final Delivery Orchestrator" in final_delivery_orchestrator
    assert "allowed_tools" in final_delivery_orchestrator
    assert "tool_contracts" in final_delivery_orchestrator
    assert "runtime feature" in semantic_judge
    assert "참고 신호" in semantic_judge
    assert "최종 의미판단" in semantic_judge
    assert "비결과 답변" in semantic_judge
    assert "물리적 안전" in semantic_judge
    assert "Blocked Delivery Recovery Agent" in blocked_recovery
    assert "fallback" in blocked_recovery
    assert "사용자 질문" in final_qa
    assert "최종 답변 후보" in final_qa
    assert "새 최종 답변" in final_qa_repair
    assert "한국어 평문" in final_qa_repair


def test_governance_plugin_loads_as_bundled_backend(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    from miho_cli.plugins import PluginManager, get_plugin_auxiliary_tasks

    manager = PluginManager()
    manager.discover_and_load()

    loaded = manager._plugins["governance_os"]
    keys = {task["key"] for task in get_plugin_auxiliary_tasks()}
    declared_hooks = set(loaded.manifest.provides_hooks)
    declared_tasks = set(loaded.manifest.provides_auxiliary_tasks)
    assert loaded.enabled
    assert {
        "pre_gateway_dispatch",
        "pre_tool_call",
        "transform_tool_result",
        "transform_llm_output",
    }.issubset(declared_hooks)
    assert {
        "miho_governance_dispatcher",
        "miho_governance_reviewer",
        "miho_governance_reviewer_academy",
        "miho_governance_reviewer_delivery",
        "miho_governance_reviewer_dev",
        "miho_governance_reviewer_research",
        "miho_governance_promotion_judge",
        "miho_self_harness_weakness_miner",
        "miho_self_harness_proposer",
        "miho_governance_final_qa",
        "miho_governance_final_qa_repair",
        "miho_governance_final_delivery",
        "miho_governance_final_delivery_orchestrator",
        "miho_governance_semantic_delivery_judge",
        "miho_governance_blocked_delivery_recovery",
    }.issubset(declared_tasks)
    assert "miho_governance_dispatcher" in keys
    assert "miho_governance_reviewer" in keys
    assert "miho_governance_reviewer_academy" in keys
    assert "miho_governance_reviewer_delivery" in keys
    assert "miho_self_harness_weakness_miner" in keys
    assert "miho_self_harness_proposer" in keys
    assert "miho_governance_final_delivery" in keys
    assert "miho_governance_final_delivery_orchestrator" in keys
    assert "miho_governance_semantic_delivery_judge" in keys
    assert "miho_governance_blocked_delivery_recovery" in keys
    assert "miho_governance_final_qa" in keys
    assert "miho_governance_final_qa_repair" in keys
