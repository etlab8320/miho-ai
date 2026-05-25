from __future__ import annotations

from types import SimpleNamespace

from agent.prompt_builder import OPENAI_MODEL_EXECUTION_GUIDANCE
from agent.system_prompt import build_system_prompt_parts


def test_discord_system_prompt_uses_soul_identity(monkeypatch):
    persona = "You are Miho AI. For Korean users, answer in natural Korean by default."

    monkeypatch.setattr("run_agent.load_soul_md", lambda: persona)
    monkeypatch.setattr("run_agent.build_nous_subscription_prompt", lambda _tools: "")
    monkeypatch.setattr("run_agent.build_environment_hints", lambda: "")
    monkeypatch.setattr("run_agent.build_context_files_prompt", lambda **_kwargs: "")

    agent = SimpleNamespace(
        load_soul_identity=False,
        skip_context_files=False,
        valid_tool_names=set(),
        _kanban_worker_guidance=False,
        _tool_use_enforcement=False,
        provider="openrouter",
        model="gpt-5.4",
        platform="discord",
        _memory_store=None,
        _memory_manager=None,
        pass_session_id=False,
        session_id="session-1",
    )

    parts = build_system_prompt_parts(agent)

    assert parts["stable"].startswith(persona)
    assert "Discord server or group chat" in parts["stable"]


def test_gpt_system_prompt_includes_accuracy_preserving_tool_economy(monkeypatch):
    monkeypatch.setattr("run_agent.load_soul_md", lambda: None)
    monkeypatch.setattr("run_agent.build_nous_subscription_prompt", lambda _tools: "")
    monkeypatch.setattr("run_agent.build_environment_hints", lambda: "")
    monkeypatch.setattr("run_agent.build_context_files_prompt", lambda **_kwargs: "")

    agent = SimpleNamespace(
        load_soul_identity=False,
        skip_context_files=True,
        valid_tool_names={"terminal"},
        _kanban_worker_guidance=False,
        _tool_use_enforcement="auto",
        provider="openrouter",
        model="gpt-5.4",
        platform="discord",
        _memory_store=None,
        _memory_manager=None,
        pass_session_id=False,
        session_id="session-1",
    )

    parts = build_system_prompt_parts(agent)

    assert OPENAI_MODEL_EXECUTION_GUIDANCE in parts["stable"]
    assert "<tool_economy>" in parts["stable"]
    assert "hardcoded assumptions" in parts["stable"]
