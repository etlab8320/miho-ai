"""Shared virtualenv discovery for install, update, and service paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def project_venv_dir(project_root: Path) -> Path | None:
    """Return a project-local .venv/venv directory, preferring .venv."""
    for name in (".venv", "venv"):
        candidate = project_root / name
        if candidate.is_dir():
            return candidate
    return None


def detect_venv_dir(project_root: Path) -> Path | None:
    """Return the active virtualenv or project-local .venv/venv directory."""
    if sys.prefix != sys.base_prefix:
        active = Path(sys.prefix)
        if active.is_dir():
            return active

    virtual_env = os.environ.get("VIRTUAL_ENV", "")
    if virtual_env:
        active = Path(virtual_env)
        if active.is_dir():
            return active

    return project_venv_dir(project_root)


def venv_scripts_dir(venv_dir: Path, *, windows: bool) -> Path:
    return venv_dir / ("Scripts" if windows else "bin")


def detect_venv_scripts_dir(project_root: Path, *, windows: bool) -> Path | None:
    venv_dir = detect_venv_dir(project_root)
    if venv_dir is None:
        return None
    scripts_dir = venv_scripts_dir(venv_dir, windows=windows)
    return scripts_dir if scripts_dir.is_dir() else None


def project_venv_scripts_dir(project_root: Path, *, windows: bool) -> Path | None:
    venv_dir = project_venv_dir(project_root)
    if venv_dir is None:
        return None
    scripts_dir = venv_scripts_dir(venv_dir, windows=windows)
    return scripts_dir if scripts_dir.is_dir() else None


def venv_python_path(venv_dir: Path, *, windows: bool) -> Path:
    executable = "python.exe" if windows else "python"
    return venv_scripts_dir(venv_dir, windows=windows) / executable
