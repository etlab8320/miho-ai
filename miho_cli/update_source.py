"""Miho AI release source helpers for installers and updates."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


OFFICIAL_REPO_SLUG = "etlab8320/miho-ai"
OFFICIAL_REPO_URL = f"https://github.com/{OFFICIAL_REPO_SLUG}.git"
OFFICIAL_REPO_URLS = {
    OFFICIAL_REPO_URL,
    f"git@github.com:{OFFICIAL_REPO_SLUG}.git",
    OFFICIAL_REPO_URL.removesuffix(".git"),
    f"git@github.com:{OFFICIAL_REPO_SLUG}",
}
DEFAULT_UPDATE_BRANCH = "main"


def configured_update_branch() -> str | None:
    """Return the branch explicitly requested by install/update environment."""
    for name in ("MIHO_UPDATE_BRANCH", "MIHO_INSTALL_BRANCH"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def remote_branch_exists(git_cmd: list[str], cwd: Path, branch: str) -> bool:
    result = subprocess.run(
        git_cmd + ["rev-parse", "--verify", f"origin/{branch}"],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def select_update_branch(git_cmd: list[str], cwd: Path, current_branch: str) -> str:
    """Pick the remote branch this installation should update from."""
    candidates: list[str] = []
    configured = configured_update_branch()
    if configured:
        candidates.append(configured)
    if current_branch and current_branch != "HEAD":
        candidates.append(current_branch)
    candidates.append(DEFAULT_UPDATE_BRANCH)

    seen: set[str] = set()
    for branch in candidates:
        if branch in seen:
            continue
        seen.add(branch)
        if remote_branch_exists(git_cmd, cwd, branch):
            return branch
    return configured or DEFAULT_UPDATE_BRANCH


def install_script_url(branch: str = DEFAULT_UPDATE_BRANCH) -> str:
    return f"https://raw.githubusercontent.com/{OFFICIAL_REPO_SLUG}/{branch}/scripts/install.sh"


def windows_install_script_url(branch: str = DEFAULT_UPDATE_BRANCH) -> str:
    return f"https://raw.githubusercontent.com/{OFFICIAL_REPO_SLUG}/{branch}/scripts/install.ps1"


def archive_zip_url(branch: str) -> str:
    return f"https://github.com/{OFFICIAL_REPO_SLUG}/archive/refs/heads/{branch}.zip"
