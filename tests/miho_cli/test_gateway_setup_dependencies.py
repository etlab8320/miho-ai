from types import SimpleNamespace

import miho_cli.gateway as gateway


def test_configured_plugin_setup_eagerly_checks_dependencies(monkeypatch, capsys):
    calls = []
    entry = SimpleNamespace(
        label="Discord",
        setup_fn=lambda: calls.append("setup"),
        check_fn=lambda: calls.append("check") or True,
        is_connected=lambda _config: True,
        install_hint="pip install 'miho-agent[discord]'",
    )

    gateway._configure_platform({"key": "discord", "_registry_entry": entry})

    assert calls == ["setup", "check"]
    out = capsys.readouterr().out
    assert "Discord dependencies ready" in out


def test_configured_plugin_setup_warns_when_dependency_check_fails(capsys):
    calls = []
    entry = SimpleNamespace(
        label="Discord",
        setup_fn=lambda: calls.append("setup"),
        check_fn=lambda: calls.append("check") or False,
        is_connected=lambda _config: True,
        install_hint="pip install 'miho-agent[discord]'",
    )

    gateway._configure_platform({"key": "discord", "_registry_entry": entry})

    assert calls == ["setup", "check"]
    out = capsys.readouterr().out
    assert "runtime dependencies are not ready" in out
    assert "miho-agent[discord]" in out
