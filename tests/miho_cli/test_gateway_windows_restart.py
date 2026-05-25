import pytest

import miho_cli.gateway as gateway
import miho_cli.gateway_windows as gateway_windows
import miho_cli.setup as setup


def test_restart_without_installed_service_direct_spawns_without_prompt(monkeypatch, capsys):
    """Restart must recover no-service gateways without an install prompt."""
    calls = []
    pids_by_check = iter([[27128], []])

    def fake_gateway_pids():
        try:
            return next(pids_by_check)
        except StopIteration:
            return []

    monkeypatch.setattr(gateway_windows, "_assert_windows", lambda: None)
    monkeypatch.setattr(gateway_windows, "is_task_registered", lambda: False)
    monkeypatch.setattr(gateway_windows, "is_startup_entry_installed", lambda: False)
    monkeypatch.setattr(gateway_windows, "_gateway_pids", fake_gateway_pids)
    monkeypatch.setattr(
        gateway_windows,
        "_exec_schtasks",
        lambda args: calls.append(("schtasks", tuple(args))) or (0, "", ""),
    )
    monkeypatch.setattr(
        gateway,
        "kill_gateway_processes",
        lambda all_profiles=False: calls.append(("kill", all_profiles)) or 1,
    )
    monkeypatch.setattr(gateway_windows.time, "sleep", lambda seconds: calls.append(("sleep", seconds)))
    monkeypatch.setattr(
        setup,
        "prompt_yes_no",
        lambda *args, **kwargs: pytest.fail("restart must not prompt to install"),
    )
    monkeypatch.setattr(gateway_windows, "_spawn_detached", lambda path=None: calls.append(("spawn", path)) or 12345)
    monkeypatch.setattr(gateway_windows, "_report_gateway_start", lambda via: calls.append(("report_start", via)))

    gateway_windows.restart()

    assert ("kill", False) in calls
    assert ("spawn", None) in calls
    assert any(call[0] == "report_start" for call in calls)
    out = capsys.readouterr().out
    assert "Gateway stopped" in out
