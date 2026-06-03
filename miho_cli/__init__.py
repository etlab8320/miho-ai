"""Miho CLI package."""

from __future__ import annotations

import os
import sys

# Single source of truth = pyproject [project].version (read via package
# metadata). Avoids the drift where pyproject was bumped but this string wasn't,
# so `miho --version` lied. Falls back to a literal only if metadata is missing
# (e.g. running from a bare source tree with no install).
try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("miho-agent")
except Exception:  # pragma: no cover - source-tree fallback
    __version__ = "1.0.38"
__release_date__ = "2026.6.3"


def _ensure_utf8() -> None:
    """Force UTF-8 stdout/stderr on Windows."""
    if sys.platform != "win32":
        return
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        try:
            if getattr(stream, "encoding", "").lower().replace("-", "") != "utf8":
                new_stream = open(
                    stream.fileno(), "w", encoding="utf-8",
                    buffering=1,
                    closefd=False,
                )
                setattr(sys, stream_name, new_stream)
        except (AttributeError, OSError):
            pass


_ensure_utf8()
