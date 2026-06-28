"""Dedupe generated MEDIA directives before gateway delivery."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Iterable, Pattern


PathMatcher = Callable[[str, set[str]], bool]


def dedupe_existing_media_directives(text: str, *, media_re: Pattern[str]) -> str:
    if "MEDIA:" not in text:
        return text
    matches = list(media_re.finditer(text))
    if len(matches) < 2:
        return text
    keep_indexes = _preferred_media_indexes(
        [(index, _clean_path(match.group("path"))) for index, match in enumerate(matches)]
    )
    if len(keep_indexes) == len(matches):
        return text

    chunks: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        chunks.append(text[cursor:match.start()])
        if index in keep_indexes:
            chunks.append(text[match.start():match.end()])
        cursor = match.end()
    chunks.append(text[cursor:])
    return re.sub(r"\n{3,}", "\n\n", "".join(chunks)).strip()


def dedupe_media_directives(
    items: Iterable[str],
    *,
    known_media_paths: set[str],
    path_matches_any: PathMatcher,
) -> list[str]:
    seen: set[str] = set()
    seen_media_paths = set(known_media_paths)
    selected_by_key: dict[tuple[str, ...], int] = {}
    selected_paths: dict[tuple[str, ...], str] = {}
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        media_path = _media_path_from_directive(item)
        if media_path:
            if path_matches_any(media_path, seen_media_paths):
                continue
            key = _media_dedupe_key(media_path)
            if key in selected_by_key:
                old_path = selected_paths[key]
                if _prefer_media_path(media_path, old_path):
                    unique[selected_by_key[key]] = item
                    selected_paths[key] = media_path
                    seen.add(item)
                continue
            selected_by_key[key] = len(unique)
            selected_paths[key] = media_path
            seen_media_paths.add(media_path)
        seen.add(item)
        unique.append(item)
    return unique


def _preferred_media_indexes(indexed_paths: list[tuple[int, str]]) -> set[int]:
    selected: dict[tuple[str, ...], tuple[int, str]] = {}
    for index, path in indexed_paths:
        key = _media_dedupe_key(path)
        current = selected.get(key)
        if current is None or _prefer_media_path(path, current[1]):
            selected[key] = (index, path)
    return {index for index, _path in selected.values()}


def _media_path_from_directive(directive: str) -> str:
    if not directive.startswith("MEDIA:"):
        return ""
    return _clean_path(directive.removeprefix("MEDIA:"))


def _media_dedupe_key(path: str) -> tuple[str, ...]:
    manifest_key = _manifest_media_dedupe_key(path)
    if manifest_key:
        return manifest_key
    clean = _clean_path(path)
    try:
        return ("exact", str(Path(clean).resolve(strict=True)))
    except (OSError, RuntimeError, ValueError):
        return ("exact", clean)


def _manifest_media_dedupe_key(path: str) -> tuple[str, ...] | None:
    try:
        media_path = Path(_clean_path(path)).resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return None
    for suffix, kind in (
        (".hakjong_validation.json", "hakjong"),
        (".practical_reco_validation.json", "practical_reco"),
    ):
        manifest_path = media_path.with_suffix(suffix)
        if not manifest_path.exists():
            continue
        payload = _read_json_manifest(manifest_path)
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            continue
        universities = payload.get("university_names") or []
        if not isinstance(universities, list):
            universities = []
        university_key = "|".join(_normalized_key_part(item) for item in universities)
        return (
            "manifest",
            kind,
            _normalized_key_part(payload.get("student_name")),
            university_key,
            _strip_retry_suffix(media_path.stem),
            media_path.suffix.lower(),
        )
    return None


def _read_json_manifest(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _clean_path(path: str) -> str:
    clean = path.strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in "`\"'":
        clean = clean[1:-1].strip()
    return os.path.expanduser(clean.rstrip('",}.)]'))


def _normalized_key_part(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def _strip_retry_suffix(stem: str) -> str:
    return re.sub(r"_[0-9]+$", "", str(stem or ""))


def _prefer_media_path(candidate: str, current: str) -> bool:
    return _media_preference(candidate) > _media_preference(current)


def _media_preference(path: str) -> tuple[float, int, str]:
    clean = _clean_path(path)
    try:
        resolved = Path(clean).resolve(strict=True)
        mtime = resolved.stat().st_mtime
        text = str(resolved)
    except (OSError, RuntimeError, ValueError):
        mtime = 0.0
        text = clean
    match = re.search(r"_([0-9]+)$", Path(clean).stem)
    return (mtime, int(match.group(1)) if match else 0, text)
