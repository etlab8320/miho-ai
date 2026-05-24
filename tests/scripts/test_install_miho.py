"""Tests for the Miho AI installer."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path


def test_install_miho_creates_native_launcher(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    bin_dir = tmp_path / "bin"
    miho_home = tmp_path / ".miho"
    env = os.environ.copy()
    env.update({
        "MIHO_BIN_DIR": str(bin_dir),
        "MIHO_HOME": str(miho_home),
    })

    result = subprocess.run(
        ["bash", str(repo_root / "scripts" / "install-miho.sh"), "--skip-sync"],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    launcher = bin_dir / "miho"
    launcher_text = launcher.read_text()
    assert "Miho AI installed." in result.stdout
    assert miho_home.is_dir()
    assert stat.S_IMODE(miho_home.stat().st_mode) == 0o700
    assert launcher.exists()
    assert 'export MIHO_RUNTIME="1"' in launcher_text
    assert 'export MIHO_BRAND="miho"' in launcher_text
    assert 'export MIHO_HOME="' in launcher_text
    assert "MIHO_DEFAULT_SKIN" not in launcher_text
    assert "exec uv run miho" in launcher_text
