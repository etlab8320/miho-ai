from miho_cli.gateway import _runtime_health_lines


def test_runtime_health_lines_include_fatal_platform_and_startup_reason(monkeypatch):
    monkeypatch.setattr(
        "gateway.status.read_runtime_status",
        lambda: {
            "gateway_state": "startup_failed",
            "exit_reason": "telegram conflict",
            "platforms": {
                "telegram": {
                    "state": "fatal",
                    "error_message": "another poller is active",
                }
            },
        },
    )

    lines = _runtime_health_lines()

    assert "⚠ telegram: another poller is active" in lines
    assert "⚠ Last startup issue: telegram conflict" in lines


def test_runtime_health_lines_include_unavailable_platform(monkeypatch):
    monkeypatch.setattr(
        "gateway.status.read_runtime_status",
        lambda: {
            "gateway_state": "running",
            "platforms": {
                "discord": {
                    "state": "unavailable",
                    "error_message": "adapter unavailable; install dependencies: pip install 'miho-agent[discord]'",
                }
            },
        },
    )

    lines = _runtime_health_lines()

    assert (
        "⚠ discord adapter: unavailable - adapter unavailable; install dependencies: "
        "pip install 'miho-agent[discord]'"
    ) in lines
