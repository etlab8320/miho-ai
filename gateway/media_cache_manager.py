"""Managed media-cache paths and retention cleanup."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

from miho_constants import get_miho_dir, get_miho_home


DEFAULT_RETENTION_DAYS = 14
_CATEGORY_SAFE_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


@dataclass(frozen=True)
class MediaCacheCleanupSummary:
    roots: tuple[str, ...]
    retention_days: int
    dry_run: bool
    scanned_files: int = 0
    candidate_files: int = 0
    deleted_files: int = 0
    deleted_dirs: int = 0
    freed_bytes: int = 0
    errors: tuple[str, ...] = ()


def media_cache_root() -> Path:
    return get_miho_dir("cache/media", "media_cache")


def media_cache_roots() -> list[Path]:
    roots = [media_cache_root(), get_miho_home() / "cache" / "media", get_miho_home() / "media_cache"]
    unique: list[Path] = []
    for root in roots:
        try:
            resolved = root.resolve(strict=False)
        except OSError:
            resolved = root
        if resolved not in unique:
            unique.append(resolved)
    return unique


def managed_media_dir(
    category: str,
    *,
    when: datetime | None = None,
    root: Path | None = None,
) -> Path:
    """Return ``media_cache/<category>/<YYYYMMDD>`` and create it."""
    safe_category = _safe_category(category)
    day = (when or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%d")
    path = (root or media_cache_root()) / safe_category / day
    path.mkdir(parents=True, exist_ok=True)
    return path


def cleanup_media_cache(
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    dry_run: bool = True,
    roots: list[Path] | None = None,
    now: datetime | None = None,
) -> MediaCacheCleanupSummary:
    """Delete files older than ``retention_days`` from Miho media caches."""
    if retention_days < 0:
        raise ValueError("retention_days must be >= 0")
    selected_roots = roots or media_cache_roots()
    safe_roots = [_require_safe_media_root(root) for root in selected_roots]
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    scanned = candidates = deleted = dirs = freed = 0
    errors: list[str] = []

    for root in safe_roots:
        if not root.exists():
            continue
        files = _iter_files(root)
        scanned += len(files)
        for file_path in files:
            if not _is_older_than(file_path, cutoff):
                continue
            candidates += 1
            try:
                size = file_path.stat().st_size
                freed += size
                if not dry_run:
                    file_path.unlink()
                    deleted += 1
            except OSError as exc:
                errors.append(f"{file_path}: {exc}")
        if not dry_run:
            dirs += _remove_empty_dirs(root, errors)

    return MediaCacheCleanupSummary(
        roots=tuple(str(root) for root in safe_roots),
        retention_days=retention_days,
        dry_run=dry_run,
        scanned_files=scanned,
        candidate_files=candidates,
        deleted_files=deleted,
        deleted_dirs=dirs,
        freed_bytes=freed,
        errors=tuple(errors),
    )


def format_cleanup_summary(summary: MediaCacheCleanupSummary) -> str:
    action = "would delete" if summary.dry_run else "deleted"
    lines = [
        "[media-cache] "
        f"{action} {summary.candidate_files if summary.dry_run else summary.deleted_files} "
        f"old file(s), freed {summary.freed_bytes} bytes.",
        f"retention_days={summary.retention_days}, roots={len(summary.roots)}",
    ]
    if summary.deleted_dirs:
        lines.append(f"empty_dirs_removed={summary.deleted_dirs}")
    if summary.errors:
        lines.append(f"errors={len(summary.errors)}")
    return "\n".join(lines)


def _safe_category(category: str) -> str:
    cleaned = _CATEGORY_SAFE_RE.sub("_", str(category or "").strip()).strip("._-").lower()
    return cleaned or "misc"


def _require_safe_media_root(root: Path) -> Path:
    resolved = root.expanduser().resolve(strict=False)
    home = get_miho_home().resolve(strict=False)
    allowed = (
        home / "cache" / "media",
        home / "media_cache",
    )
    for allowed_root in allowed:
        try:
            resolved.relative_to(allowed_root.resolve(strict=False))
            return resolved
        except ValueError:
            continue
    raise ValueError(f"Unsafe media cache root: {root}")


def _iter_files(root: Path) -> list[Path]:
    try:
        return [path for path in root.rglob("*") if path.is_file()]
    except OSError:
        return []


def _is_older_than(path: Path, cutoff: datetime) -> bool:
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
    except OSError:
        return False
    return modified < cutoff


def _remove_empty_dirs(root: Path, errors: list[str]) -> int:
    removed = 0
    try:
        dirs = [path for path in root.rglob("*") if path.is_dir()]
    except OSError as exc:
        errors.append(f"{root}: {exc}")
        return 0
    for directory in sorted(dirs, key=lambda p: len(p.parts), reverse=True):
        try:
            directory.rmdir()
            removed += 1
        except OSError:
            continue
    return removed
