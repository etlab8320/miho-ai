"""Thread-stored academy roster lookup."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from gateway.discord_workspace import ensure_workspace_for_source

from .context import current_event_context


_MAX_FILE_CHARS = 80_000
_HEADING_PATTERN = re.compile(r"^#{2,6}\s+(.+)$")
_BULLET_PATTERN = re.compile(r"^[-*]\s+(.+)$")
_INLINE_ROSTER_PATTERN = re.compile(r"^(.+?(?:반|명단|편성표))\s*(?:[:：]|[-–—])\s*(.+)$")
_NAME_SEPARATOR_PATTERN = re.compile(r"\s*[,，、/|]\s*|\s+[·ㆍ]\s+")


def _clean_heading(text: str) -> str:
    value = re.sub(r"[*_`#]+", "", str(text or ""))
    return re.sub(r"\s+", " ", value).strip()


def _match_key(text: str) -> str:
    value = _clean_heading(text)
    return re.sub(r"[\s·/_-]+", "", value).casefold()


def _split_names(text: str) -> list[str]:
    names: list[str] = []
    for raw in _NAME_SEPARATOR_PATTERN.split(str(text or "")):
        name = _clean_heading(raw)
        if name:
            names.append(name)
    return names


def _append_names(rosters: dict[str, list[str]], roster: str, names: list[str]) -> None:
    bucket = rosters.setdefault(roster, [])
    for name in names:
        if name not in bucket:
            bucket.append(name)


def parse_markdown_rosters(markdown: str) -> dict[str, list[str]]:
    """Parse Markdown headings with bullet-list names into roster groups."""
    rosters: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in str(markdown or "").splitlines():
        line = raw_line.strip()
        inline = _INLINE_ROSTER_PATTERN.match(line)
        if inline:
            current = _clean_heading(inline.group(1))
            _append_names(rosters, current, _split_names(inline.group(2)))
            continue
        heading = _HEADING_PATTERN.match(line)
        if heading:
            current = _clean_heading(heading.group(1))
            rosters.setdefault(current, [])
            continue
        bullet = _BULLET_PATTERN.match(line)
        if not current or not bullet:
            continue
        item = _clean_heading(bullet.group(1))
        if item:
            _append_names(rosters, current, [item])
    return {name: names for name, names in rosters.items() if names}


def _current_thread_dir() -> Path | None:
    event = current_event_context()
    source = getattr(event, "source", None)
    workspace = ensure_workspace_for_source(source)
    return workspace.active_dir if workspace else None


def _workspace_markdown_files(thread_dir: Path) -> list[Path]:
    work_dir = thread_dir / "work"
    return sorted(work_dir.glob("*.md")) if work_dir.exists() else []


def _read_rosters(thread_dir: Path) -> tuple[dict[str, list[str]], list[str]]:
    merged: dict[str, list[str]] = {}
    sources: list[str] = []
    for path in _workspace_markdown_files(thread_dir):
        try:
            text = path.read_text(encoding="utf-8")[:_MAX_FILE_CHARS]
        except OSError:
            continue
        parsed = parse_markdown_rosters(text)
        if not parsed:
            continue
        sources.append(str(path))
        for roster, names in parsed.items():
            bucket = merged.setdefault(roster, [])
            for name in names:
                if name not in bucket:
                    bucket.append(name)
    return merged, sources


def _select_rosters(
    rosters: dict[str, list[str]],
    requested: list[str],
) -> dict[str, list[str]]:
    if not requested:
        return rosters
    by_key = {_match_key(name): name for name in rosters}
    selected: dict[str, list[str]] = {}
    for raw in requested:
        key = _match_key(raw)
        matched = by_key.get(key)
        if matched:
            selected[matched] = rosters[matched]
    return selected


def _duplicates(rosters: dict[str, list[str]]) -> dict[str, list[str]]:
    seen: dict[str, list[str]] = {}
    display: dict[str, str] = {}
    for roster, names in rosters.items():
        for name in names:
            key = _match_key(name)
            display.setdefault(key, name)
            seen.setdefault(key, []).append(roster)
    return {display[key]: groups for key, groups in seen.items() if len(groups) > 1}


def _message(rosters: dict[str, list[str]], duplicates: dict[str, list[str]]) -> str:
    if not rosters:
        return "현재 스레드에 저장된 편성표에서 요청한 반 명단은 아직 안 보여."
    parts = ["현재 스레드 편성표 기준이야."]
    for roster, names in rosters.items():
        parts.append(f"\n{roster}")
        parts.extend(f"- {name}" for name in names)
    if duplicates:
        parts.append("\n중복 배정")
        parts.extend(f"- {name}: {', '.join(groups)}" for name, groups in duplicates.items())
    return "\n".join(parts)


def _thread_roster_lookup_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    requested = payload.get("roster_names") if isinstance(payload.get("roster_names"), list) else []
    requested_names = [str(name).strip() for name in requested if str(name).strip()]
    thread_dir = _current_thread_dir()
    if thread_dir is None:
        result = {
            "ok": True,
            "found": False,
            "rosters": {},
            "duplicates": {},
            "message": "현재 Discord 스레드 작업공간을 확인할 수 없어.",
        }
        return json.dumps(result, ensure_ascii=False)
    rosters, sources = _read_rosters(thread_dir)
    selected = _select_rosters(rosters, requested_names)
    dupes = _duplicates(selected)
    result = {
        "ok": True,
        "found": bool(selected),
        "rosters": selected,
        "duplicates": dupes,
        "source_paths": sources,
        "message": _message(selected, dupes),
    }
    return json.dumps(result, ensure_ascii=False)


def register_thread_roster_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_thread_roster_lookup",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "roster_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "현재 Discord 스레드 작업파일에서 확인할 반/명단 이름.",
                },
            },
            "additionalProperties": False,
        },
        handler=_thread_roster_lookup_tool_handler,
        description=(
            "현재 Discord 스레드에 저장된 작업파일(work/*.md)의 반 편성표/명단을 조회한다. "
            "사용자가 '스레드에 저장해둔 반 명단', '편성표', '정시반 명단', '방금 추가한 명단'을 묻는 경우 "
            "학원 DB보다 이 도구를 먼저 사용한다. 특정 날짜의 수업 배정 명단은 academy_class_roster_range, "
            "학원 DB 범용 조회는 academy_api_query를 사용한다."
        ),
    )
