from pathlib import Path
from types import SimpleNamespace


def test_update_venv_scripts_dir_supports_dot_venv(tmp_path, monkeypatch):
    """Update repair/prefetch paths should work in .venv-based dev installs."""
    import miho_cli.main as cli_main

    dot_venv_bin = tmp_path / ".venv" / "bin"
    dot_venv_bin.mkdir(parents=True)

    monkeypatch.setattr(cli_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli_main, "_is_windows", lambda: False)

    assert cli_main._venv_scripts_dir() == dot_venv_bin


def test_update_venv_scripts_dir_prefers_dot_venv_over_venv(tmp_path, monkeypatch):
    import miho_cli.main as cli_main

    dot_venv_bin = tmp_path / ".venv" / "bin"
    venv_bin = tmp_path / "venv" / "bin"
    dot_venv_bin.mkdir(parents=True)
    venv_bin.mkdir(parents=True)

    monkeypatch.setattr(cli_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli_main, "_is_windows", lambda: False)

    assert cli_main._venv_scripts_dir() == dot_venv_bin


def test_update_venv_scripts_dir_supports_windows_layout(tmp_path, monkeypatch):
    import miho_cli.main as cli_main

    scripts = tmp_path / "venv" / "Scripts"
    scripts.mkdir(parents=True)

    monkeypatch.setattr(cli_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli_main, "_is_windows", lambda: True)

    assert cli_main._venv_scripts_dir() == scripts


def test_reinstall_python_package_uses_detected_dot_venv_for_uv(tmp_path, monkeypatch):
    import miho_cli.main as cli_main

    dot_venv_bin = tmp_path / ".venv" / "bin"
    dot_venv_bin.mkdir(parents=True)

    captured_envs = []
    subprocess_calls = []

    monkeypatch.setattr(cli_main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(cli_main.shutil, "which", lambda name: "/usr/bin/uv" if name == "uv" else None)
    monkeypatch.setattr(cli_main, "_is_termux_env", lambda env=None: False)
    monkeypatch.setattr(cli_main, "_is_android_python", lambda: False)
    monkeypatch.setattr(cli_main, "_update_node_dependencies", lambda: None)
    monkeypatch.setattr(cli_main, "_build_web_ui", lambda _path: None)

    def fake_install(_cmd, *, env=None, group="all"):
        captured_envs.append(env)

    def fake_run(cmd, **kwargs):
        subprocess_calls.append((cmd, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli_main, "_install_python_dependencies_with_optional_fallback", fake_install)
    monkeypatch.setattr(cli_main.subprocess, "run", fake_run)

    cli_main._reinstall_python_package()

    assert captured_envs
    assert captured_envs[0]["VIRTUAL_ENV"] == str(tmp_path / ".venv")
    assert subprocess_calls[0][1]["env"]["VIRTUAL_ENV"] == str(tmp_path / ".venv")
