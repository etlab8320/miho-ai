"""Resolve MIHO_HOME for standalone skill scripts.

Skill scripts may run outside the Miho process (e.g. system Python,
nix env, CI) where ``miho_constants`` is not importable.  This module
provides the same ``get_miho_home()`` and ``display_miho_home()``
contracts as ``miho_constants`` without requiring it on ``sys.path``.

When ``miho_constants`` IS available it is used directly so that any
future enhancements (profile resolution, Docker detection, etc.) are
picked up automatically.  The fallback path replicates the core logic
from ``miho_constants.py`` using only the stdlib.

All scripts under ``google-workspace/scripts/`` should import from here
instead of duplicating the ``MIHO_HOME = Path(os.getenv(...))`` pattern.
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from miho_constants import display_miho_home as display_miho_home
    from miho_constants import get_miho_home as get_miho_home
except (ModuleNotFoundError, ImportError):

    def get_miho_home() -> Path:
        """Return the Miho home directory (default: ~/.miho).

        Mirrors ``miho_constants.get_miho_home()``."""
        val = os.environ.get("MIHO_HOME", "").strip()
        return Path(val) if val else Path.home() / ".miho"

    def display_miho_home() -> str:
        """Return a user-friendly ``~/``-shortened display string.

        Mirrors ``miho_constants.display_miho_home()``."""
        home = get_miho_home()
        try:
            return "~/" + str(home.relative_to(Path.home()))
        except ValueError:
            return str(home)
