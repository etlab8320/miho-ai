"""Resolve generated media paths before native platform upload."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import unquote, urlparse


ValidatePath = Callable[[str, Iterable[Path] | None], str | None]


_ROOT_METADATA_KEYS = (
    "media_delivery_roots",
    "media_delivery_root",
    "thread_workspace_dir",
    "discord_workspace_dir",
    "workspace_dir",
    "work_dir",
    "working_dir",
)


def normalize_media_path(value: str) -> str:
    """Return a path-like string stripped of model formatting noise."""
    candidate = str(value or "").strip()
    if len(candidate) >= 2 and candidate[0] == candidate[-1] and candidate[0] in "`\"'":
        candidate = candidate[1:-1].strip()
    candidate = candidate.lstrip("`\"'").rstrip("`\"',.;:)}]")
    if candidate.startswith("file://"):
        parsed = urlparse(candidate)
        if parsed.netloc and parsed.netloc not in {"localhost", "127.0.0.1"}:
            return ""
        candidate = unquote(parsed.path)
    return os.path.expanduser(candidate.strip())


def metadata_delivery_roots(metadata: dict[str, Any] | None) -> list[Path]:
    """Extract safe per-turn workspace roots from send metadata."""
    if not isinstance(metadata, dict):
        return []
    roots: list[Path] = []
    for key in _ROOT_METADATA_KEYS:
        raw = metadata.get(key)
        if not raw:
            continue
        values = raw if isinstance(raw, (list, tuple, set)) else [raw]
        for value in values:
            path = Path(os.path.expanduser(str(value))).resolve(strict=False)
            if path not in roots:
                roots.append(path)
    return roots


def resolve_media_delivery_path(
    value: str,
    *,
    validate_path: ValidatePath,
    allowed_roots: Iterable[Path],
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Resolve a model-provided media path to a safe absolute upload path.

    The model may emit a basename from Miho caches (``report.pdf``), a path
    relative to the active Discord workspace (``exports/report.pdf``), or an
    absolute path. The caller-provided validator remains the final authority.
    """
    candidate = normalize_media_path(value)
    if not candidate:
        return None

    meta_roots = metadata_delivery_roots(metadata)
    base_roots = [Path(root) for root in allowed_roots]
    extra_roots = meta_roots

    attempts: list[Path] = []
    raw_path = Path(candidate)
    if raw_path.is_absolute():
        attempts.append(raw_path)
    else:
        for root in [*meta_roots, *base_roots]:
            attempts.append(root / raw_path)

    basename = raw_path.name
    allow_basename_fallback = not raw_path.is_absolute() or not raw_path.exists()
    if basename and allow_basename_fallback:
        for root in [*meta_roots, *base_roots]:
            attempts.append(root / basename)
        for root in meta_roots:
            attempts.extend(_recursive_name_matches(root, basename))

    seen: set[str] = set()
    for attempt in attempts:
        key = str(attempt)
        if key in seen:
            continue
        seen.add(key)
        resolved = validate_path(str(attempt), extra_roots)
        if resolved:
            return resolved
    return None


def _recursive_name_matches(root: Path, basename: str) -> list[Path]:
    if not basename:
        return []
    try:
        if not root.exists() or not root.is_dir():
            return []
        return [path for path in root.rglob(basename) if path.is_file()]
    except OSError:
        return []
