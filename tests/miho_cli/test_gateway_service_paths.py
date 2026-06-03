from pathlib import Path
from unittest.mock import patch


def test_service_path_skips_nonexistent_node_modules(tmp_path):
    """Service PATH should not include node_modules/.bin if it doesn't exist."""
    from miho_cli.gateway import _build_service_path_dirs
    with patch("miho_cli.gateway.get_miho_home", return_value=tmp_path / ".miho"):
        dirs = _build_service_path_dirs(project_root=tmp_path)
    node_modules_bin = str(tmp_path / "node_modules" / ".bin")
    assert node_modules_bin not in dirs


def test_service_path_includes_node_modules_when_present(tmp_path):
    """Service PATH should include node_modules/.bin when it exists."""
    nm_bin = tmp_path / "node_modules" / ".bin"
    nm_bin.mkdir(parents=True)
    from miho_cli.gateway import _build_service_path_dirs
    with patch("miho_cli.gateway.get_miho_home", return_value=tmp_path / ".miho"):
        dirs = _build_service_path_dirs(project_root=tmp_path)
    assert str(nm_bin) in dirs


def test_service_path_includes_dot_venv_bin_when_present(tmp_path):
    """Service PATH should match dev checkouts that use .venv instead of venv."""
    dot_venv_bin = tmp_path / ".venv" / "bin"
    dot_venv_bin.mkdir(parents=True)
    from miho_cli.gateway import _build_service_path_dirs
    with patch("miho_cli.gateway.get_miho_home", return_value=tmp_path / ".miho"):
        dirs = _build_service_path_dirs(project_root=tmp_path)
    assert str(dot_venv_bin) in dirs


def test_service_path_includes_miho_home_node_modules(tmp_path):
    """Service PATH should include ~/.miho/node_modules/.bin when it exists."""
    miho_nm = tmp_path / ".miho" / "node_modules" / ".bin"
    miho_nm.mkdir(parents=True)
    from miho_cli.gateway import _build_service_path_dirs
    with patch("miho_cli.gateway.get_miho_home", return_value=tmp_path / ".miho"):
        dirs = _build_service_path_dirs(project_root=tmp_path)
    assert str(miho_nm) in dirs
