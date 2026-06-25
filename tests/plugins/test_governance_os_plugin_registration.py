"""Plugin registration contract tests for Governance OS."""

from __future__ import annotations

from typing import Any

from plugins import governance_os


class _Ctx:
    def __init__(self) -> None:
        self.tasks: list[dict[str, Any]] = []
        self.hooks: list[str] = []

    def register_auxiliary_task(self, key: str, **kwargs: Any) -> None:
        self.tasks.append({"key": key, **kwargs})

    def register_hook(self, hook_name: str, callback: Any) -> None:
        del callback
        self.hooks.append(hook_name)


def test_governance_plugin_registers_auxiliary_judge_tasks() -> None:
    ctx = _Ctx()

    governance_os.register(ctx)

    keys = {task["key"] for task in ctx.tasks}
    assert {
        "miho_governance_dispatcher",
        "miho_governance_reviewer",
        "miho_governance_promotion_judge",
    }.issubset(keys)
    assert "pre_gateway_dispatch" in ctx.hooks
    assert "pre_tool_call" in ctx.hooks
    assert "transform_tool_result" in ctx.hooks
    assert "transform_llm_output" in ctx.hooks


def test_governance_auxiliary_tasks_include_operational_instructions() -> None:
    ctx = _Ctx()

    governance_os.register(ctx)

    tasks = {task["key"]: task for task in ctx.tasks}
    dispatcher = tasks["miho_governance_dispatcher"]["defaults"]["instructions"]
    reviewer = tasks["miho_governance_reviewer"]["defaults"]["instructions"]
    promotion = tasks["miho_governance_promotion_judge"]["defaults"]["instructions"]

    assert "playbook" in dispatcher
    assert "required_tools" in dispatcher
    assert "후검증" in reviewer
    assert "retry_tools" in reviewer
    assert "반복 실패" in promotion
    assert "rollback" in promotion


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
        "miho_governance_promotion_judge",
    }.issubset(declared_tasks)
    assert "miho_governance_dispatcher" in keys
    assert "miho_governance_reviewer" in keys
