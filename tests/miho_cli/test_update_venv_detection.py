from pathlib import Path


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
