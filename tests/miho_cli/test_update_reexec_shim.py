"""Tests for the Windows self-replace fix in `miho update`.

When `miho update` runs through the `miho.exe` console-script shim on Windows,
the launcher holds an open handle on the very file uv must overwrite when it
re-creates the entry point during `pip install -e .` — Windows blocks the
replace with `os error 32`. The fix re-execs the update through the venv's
`python.exe` (which holds no handle on `miho.exe`) so uv can replace the shim.

These tests force `_is_windows` / `sys.argv` / `sys.executable` via patching so
the Windows-only path can be exercised on any host. subprocess is always mocked
— no real update ever runs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from miho_cli import main as cli_main


def _args(**over):
    base = dict(
        check=False,
        gateway=False,
        yes=False,
        force=False,
        backup=False,
        no_backup=False,
        reexec_guard=False,
    )
    base.update(over)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# _running_as_miho_exe_shim
# ---------------------------------------------------------------------------


@patch.object(cli_main, "_is_windows", return_value=True)
def test_running_as_shim_true_when_argv0_is_miho_exe(_winp, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "miho.exe"), "update"])
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    assert cli_main._running_as_miho_exe_shim() is True


@patch.object(cli_main, "_is_windows", return_value=True)
def test_running_as_shim_true_when_executable_is_gateway_exe(_winp, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["something"])
    monkeypatch.setattr(sys, "executable", str(tmp_path / "miho-gateway.exe"))
    assert cli_main._running_as_miho_exe_shim() is True


@patch.object(cli_main, "_is_windows", return_value=True)
def test_running_as_shim_false_when_python(_winp, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["-m", "miho_cli.main", "update"])
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    assert cli_main._running_as_miho_exe_shim() is False


@patch.object(cli_main, "_is_windows", return_value=False)
def test_running_as_shim_false_off_windows(_winp, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["/venv/bin/miho.exe", "update"])
    assert cli_main._running_as_miho_exe_shim() is False


# ---------------------------------------------------------------------------
# _maybe_reexec_update_off_exe_shim — trigger conditions
# ---------------------------------------------------------------------------


@patch.object(cli_main, "_is_windows", return_value=True)
def test_reexec_triggers_on_windows_via_exe_shim(_winp, tmp_path, monkeypatch):
    """win32 + miho.exe + no guard → spawns python.exe and exits with its code."""
    scripts_dir = tmp_path
    (scripts_dir / "python.exe").write_bytes(b"")

    monkeypatch.setattr(sys, "argv", [str(scripts_dir / "miho.exe"), "update"])
    fake_execve = MagicMock(side_effect=SystemExit(7))

    with patch.object(
        cli_main, "_venv_scripts_dir", return_value=scripts_dir
    ), patch.object(cli_main.os, "execve", fake_execve):
        with pytest.raises(SystemExit) as exc:
            cli_main._maybe_reexec_update_off_exe_shim(_args(force=True))

    assert exc.value.code == 7
    fake_execve.assert_called_once()
    child_argv = fake_execve.call_args.args[1]
    # Hands off to python.exe running the module, NOT miho.exe.
    assert child_argv[0] == str(scripts_dir / "python.exe")
    assert child_argv[1:4] == ["-m", "miho_cli.main", "update"]
    # Re-exec guard flag is appended → child won't loop.
    assert "--reexec-guard" in child_argv
    # Behaviour flag forwarded.
    assert "--force" in child_argv
    # Guard env set for belt-and-suspenders loop protection.
    assert fake_execve.call_args.args[2]["MIHO_UPDATE_REEXECED"] == "1"


@patch.object(cli_main, "_is_windows", return_value=True)
def test_reexec_skipped_when_guard_flag_present(_winp, tmp_path, monkeypatch):
    """--reexec-guard already set → no second spawn (infinite-loop guard)."""
    scripts_dir = tmp_path
    (scripts_dir / "python.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "argv", [str(scripts_dir / "miho.exe"), "update"])
    fake_run = MagicMock()

    with patch.object(
        cli_main, "_venv_scripts_dir", return_value=scripts_dir
    ), patch.object(cli_main.subprocess, "run", fake_run):
        cli_main._maybe_reexec_update_off_exe_shim(_args(reexec_guard=True))

    fake_run.assert_not_called()


@patch.object(cli_main, "_is_windows", return_value=True)
def test_reexec_skipped_when_guard_env_present(_winp, tmp_path, monkeypatch):
    """MIHO_UPDATE_REEXECED=1 → no spawn even without the flag."""
    scripts_dir = tmp_path
    (scripts_dir / "python.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "argv", [str(scripts_dir / "miho.exe"), "update"])
    monkeypatch.setenv("MIHO_UPDATE_REEXECED", "1")
    fake_run = MagicMock()

    with patch.object(
        cli_main, "_venv_scripts_dir", return_value=scripts_dir
    ), patch.object(cli_main.subprocess, "run", fake_run):
        cli_main._maybe_reexec_update_off_exe_shim(_args())

    fake_run.assert_not_called()


@patch.object(cli_main, "_is_windows", return_value=True)
def test_reexec_skipped_when_running_via_python(_winp, tmp_path, monkeypatch):
    """Already running through python (not the .exe shim) → no spawn."""
    scripts_dir = tmp_path
    (scripts_dir / "python.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "argv", ["-m", "miho_cli.main", "update"])
    monkeypatch.setattr(sys, "executable", str(scripts_dir / "python.exe"))
    fake_run = MagicMock()

    with patch.object(
        cli_main, "_venv_scripts_dir", return_value=scripts_dir
    ), patch.object(cli_main.subprocess, "run", fake_run):
        cli_main._maybe_reexec_update_off_exe_shim(_args())

    fake_run.assert_not_called()


@patch.object(cli_main, "_is_windows", return_value=False)
def test_reexec_skipped_off_windows(_winp, tmp_path, monkeypatch):
    """POSIX replaces running images fine → re-exec must NOT happen (zero regression)."""
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "miho.exe"), "update"])
    fake_run = MagicMock()

    with patch.object(cli_main.subprocess, "run", fake_run):
        cli_main._maybe_reexec_update_off_exe_shim(_args())

    fake_run.assert_not_called()


@patch.object(cli_main, "_is_windows", return_value=True)
def test_reexec_falls_back_to_sys_executable_when_no_venv_python(
    _winp, tmp_path, monkeypatch
):
    """No venv python.exe but sys.executable is a real python → hand off to it."""
    real_py = str(tmp_path / "sys_python.exe")
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "miho.exe"), "update"])
    monkeypatch.setattr(sys, "executable", real_py)
    fake_execve = MagicMock(side_effect=SystemExit(0))

    with patch.object(
        cli_main, "_venv_scripts_dir", return_value=None
    ), patch.object(cli_main.os, "execve", fake_execve):
        with pytest.raises(SystemExit) as exc:
            cli_main._maybe_reexec_update_off_exe_shim(_args())

    assert exc.value.code == 0
    assert fake_execve.call_args.args[1][0] == real_py


@patch.object(cli_main, "_is_windows", return_value=True)
def test_reexec_continues_in_process_when_no_python_resolvable(
    _winp, tmp_path, monkeypatch, capsys
):
    """No venv python AND sys.executable is itself a shim → warn, no spawn, return."""
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "miho.exe"), "update"])
    monkeypatch.setattr(sys, "executable", str(tmp_path / "miho.exe"))
    fake_run = MagicMock()

    with patch.object(
        cli_main, "_venv_scripts_dir", return_value=None
    ), patch.object(cli_main.subprocess, "run", fake_run):
        # Returns normally (does not exit) so the in-process update still runs.
        cli_main._maybe_reexec_update_off_exe_shim(_args())

    fake_run.assert_not_called()
    assert "python.exe" in capsys.readouterr().out.lower()


# ---------------------------------------------------------------------------
# _reexec_update_arg_tokens
# ---------------------------------------------------------------------------


def test_arg_tokens_forwards_only_behaviour_flags():
    tokens = cli_main._reexec_update_arg_tokens(
        _args(yes=True, force=True, backup=True, no_backup=False, gateway=True)
    )
    assert "--yes" in tokens
    assert "--force" in tokens
    assert "--backup" in tokens
    assert "--no-backup" not in tokens
    # gateway IPC belongs to the original process and is not forwarded.
    assert "--gateway" not in tokens
    # The guard flag is appended by the caller, not here.
    assert "--reexec-guard" not in tokens
