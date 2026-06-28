"""Tests for the ``transform_llm_output`` plugin hook.

The hook fires inside ``AIAgent.run_conversation`` once the tool-calling
loop has produced a final response. Driving the full agent loop from a
unit test would be prohibitively heavy, so these tests exercise the
invoke_hook dispatch semantics that the wiring in ``run_agent.py``
depends on:

    for _hook_result in _transform_results:
        if isinstance(_hook_result, str) and _hook_result:
            final_response = _hook_result
            break  # First non-empty string wins

Mirrors ``test_transform_tool_result_hook.py`` which tests the equivalent
contract for the generic tool-result seam.
"""

from pathlib import Path

import yaml

from agent import final_output_hooks
import miho_cli.plugins as plugins_mod
from miho_cli.plugins import PluginManager, VALID_HOOKS


def _make_enabled_plugin(miho_home: Path, name: str, register_body: str) -> Path:
    """Create a plugin under <miho_home>/plugins/<name> and opt it in."""
    plugin_dir = miho_home / "plugins" / name
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.yaml").write_text(
        yaml.safe_dump({"name": name, "version": "0.1.0"}), encoding="utf-8",
    )
    (plugin_dir / "__init__.py").write_text(
        "def register(ctx):\n"
        f"    {register_body}\n",
        encoding="utf-8",
    )
    cfg_path = miho_home / "config.yaml"
    cfg = {}
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
    cfg.setdefault("plugins", {}).setdefault("enabled", []).append(name)
    cfg_path.write_text(yaml.safe_dump(cfg), encoding="utf-8")
    return plugin_dir


def test_transform_llm_output_in_valid_hooks():
    assert "transform_llm_output" in VALID_HOOKS


def test_hook_receives_expected_kwargs(tmp_path, monkeypatch):
    """Hook callback should see response_text + session_id + model + platform."""
    miho_home = tmp_path / "miho_test"
    miho_home.mkdir(exist_ok=True)
    _make_enabled_plugin(
        miho_home, "capture_hook",
        register_body=(
            'ctx.register_hook("transform_llm_output", '
            'lambda **kw: f"{kw[\'response_text\']}|{kw[\'session_id\']}|'
            '{kw[\'model\']}|{kw[\'platform\']}")'
        ),
    )
    monkeypatch.setenv("MIHO_HOME", str(miho_home))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "transform_llm_output",
        response_text="hello world",
        session_id="s1",
        model="anthropic/claude-sonnet-4.6",
        platform="cli",
    )
    assert results == ["hello world|s1|anthropic/claude-sonnet-4.6|cli"]


def test_final_output_hook_runner_passes_original_user_message_to_transform_hook():
    captured = {}

    def capture_runner(hook_name, **kwargs):
        captured["hook_name"] = hook_name
        captured["kwargs"] = kwargs
        return []

    final_output_hooks.apply_transform_llm_output_hooks(
        response_text="original",
        user_message="hello",
        conversation_history=[{"role": "user", "content": "hello"}],
        session_id="s1",
        model="m",
        platform="discord",
        invoke_hook=capture_runner,
    )

    assert captured["hook_name"] == "transform_llm_output"
    assert captured["kwargs"]["user_message"] == "hello"
    assert captured["kwargs"]["conversation_history"] == [{"role": "user", "content": "hello"}]


def test_first_non_empty_string_wins_semantics():
    """The runner keeps the first non-empty string hook result."""
    final_response = final_output_hooks.apply_transform_llm_output_hooks(
        response_text="original",
        user_message="hello",
        conversation_history=[],
        session_id="s1",
        model="m",
        platform="cli",
        invoke_hook=lambda *_args, **_kwargs: [None, "", {"bad": True}, 123, "first-winner"],
    )

    assert final_response == "first-winner"


def test_empty_string_return_leaves_response_unchanged():
    """Empty string must not replace the response (pass-through signal)."""
    final_response = final_output_hooks.apply_transform_llm_output_hooks(
        response_text="original",
        user_message="hello",
        conversation_history=[],
        session_id="s1",
        model="m",
        platform="cli",
        invoke_hook=lambda *_args, **_kwargs: [""],
    )

    assert final_response == "original"


def test_runner_exception_uses_governance_fallback_for_messaging(monkeypatch):
    """A broken hook runner must not fail-open on gateway surfaces."""
    calls = []

    def broken_runner(*_args, **_kwargs):
        raise RuntimeError("plugin invoke unavailable")

    def fake_governance_transform(response_text="", **context):
        calls.append({"response_text": response_text, **context})
        return "현재 결론: 확정 산출물 없음.\n필요한 입력: 요청을 판단할 원자료."

    monkeypatch.setattr(
        "plugins.governance_os.delivery_gate.governance_transform_llm_output",
        fake_governance_transform,
    )

    final_response = final_output_hooks.apply_transform_llm_output_hooks(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        conversation_history=[],
        session_id="s1",
        model="m",
        platform="discord",
        invoke_hook=broken_runner,
    )

    assert final_response.startswith("현재 결론:")
    assert calls
    assert calls[0]["platform"] == "discord"


def test_gateway_governance_fallback_none_uses_safe_current_result(monkeypatch):
    """Gateway surfaces must not return the unreviewed original after fallback failure."""

    def broken_runner(*_args, **_kwargs):
        raise RuntimeError("plugin invoke unavailable")

    def empty_governance_transform(response_text="", **_context):
        return None

    monkeypatch.setattr(
        "plugins.governance_os.delivery_gate.governance_transform_llm_output",
        empty_governance_transform,
    )

    final_response = final_output_hooks.apply_transform_llm_output_hooks(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        conversation_history=[],
        session_id="s1",
        model="m",
        platform="discord",
        invoke_hook=broken_runner,
    )

    assert final_response == "현재 결론: 확정 산출물 없음.\n필요한 입력: 요청을 판단할 원자료."


def test_hook_exception_does_not_replace_response(tmp_path, monkeypatch):
    """A plugin raising an exception must not break hook dispatch.

    PluginManager.invoke_hook catches per-callback exceptions, logs a
    warning, and continues — so a raising plugin contributes no entry
    to the results list, and the walk in run_agent.py finds nothing to
    replace with.
    """
    miho_home = tmp_path / "miho_test"
    miho_home.mkdir(exist_ok=True)
    _make_enabled_plugin(
        miho_home, "raising_hook",
        register_body=(
            'def _boom(**kw):\n'
            '        raise RuntimeError("boom")\n'
            '    ctx.register_hook("transform_llm_output", _boom)'
        ),
    )
    monkeypatch.setenv("MIHO_HOME", str(miho_home))

    mgr = PluginManager()
    mgr.discover_and_load()

    results = mgr.invoke_hook(
        "transform_llm_output",
        response_text="keep me",
        session_id="s1",
        model="m",
        platform="cli",
    )

    final_response = "keep me"
    for _hook_result in results:
        if isinstance(_hook_result, str) and _hook_result:
            final_response = _hook_result
            break

    assert final_response == "keep me"


def test_no_plugins_returns_empty_results(tmp_path, monkeypatch):
    """With no plugins loaded, invoke_hook returns [] and the response is unchanged."""
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_empty"))
    plugins_mod._plugin_manager = PluginManager()

    mgr = plugins_mod._plugin_manager
    results = mgr.invoke_hook(
        "transform_llm_output",
        response_text="unchanged",
        session_id="",
        model="m",
        platform="",
    )
    assert results == []
