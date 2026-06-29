"""Student binding helpers for Discord student-specific academy threads.

A binding is intentionally thread-scoped (not user-scoped): in a student
thread, every authorised user should inherit the same default student unless a
message explicitly names another student.  The binding only stores local Miho
routing metadata; it never mutates PACA/Peak/생기부 source systems.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home

_THREAD_NAME_RE = re.compile(r"^[가-힣]{2,5}$")
_BINDING_DB_OVERRIDE: Path | None = None
_CLEARED_SOURCE = "cleared"


def _db_path() -> Path:
    return get_miho_home() / "academy_ops" / "student_thread_bindings.sqlite3"


def _get_db_path() -> Path:
    return _BINDING_DB_OVERRIDE if _BINDING_DB_OVERRIDE is not None else _db_path()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ensure_schema(db: Path) -> None:
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS student_thread_binding (
                scope_key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def thread_binding_scope_key_from_source(source: Any) -> str:
    platform = str(getattr(getattr(source, "platform", None), "value", "") or "")
    guild_id = str(getattr(source, "guild_id", "") or "")
    chat_id = str(getattr(source, "chat_id", "") or "")
    thread_id = str(getattr(source, "thread_id", "") or "")
    if not thread_id:
        return ""
    parent_chat_id = str(getattr(source, "parent_chat_id", "") or "")
    # For Discord thread sources, chat_id may already be the thread id.  The
    # parent channel id is more stable for the thread scope when present.
    channel_id = parent_chat_id or chat_id
    return ":".join([platform, guild_id, channel_id, thread_id])


def context_key_prefix_for_thread(source: Any) -> str:
    scope_key = thread_binding_scope_key_from_source(source)
    return f"{scope_key}:" if scope_key else ""


def thread_name_from_source(source: Any) -> str:
    if not getattr(source, "thread_id", None):
        return ""
    return str(getattr(source, "chat_name", "") or "").strip()


def normalize_student_name(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[\s_\-]+", " ", text).strip()
    # Student threads are expected to be named directly after the student.  If
    # an operator passes a longer phrase to the manual command, use the first
    # clean Korean-name token and leave source='manual'.
    for token in text.split():
        token = token.strip(" .,!?~!ㅋㅎ()[]{}")
        if _THREAD_NAME_RE.fullmatch(token):
            return token
    return text


def looks_like_student_thread_name(value: str) -> bool:
    return bool(_THREAD_NAME_RE.fullmatch(str(value or "").strip()))


def _workspace_channel_name(source: Any) -> str:
    direct = str(getattr(source, "parent_chat_name", "") or "").strip()
    if direct:
        return direct
    try:
        from gateway.discord_workspace_paths import child_by_id, discord_root

        guild_id = str(getattr(source, "guild_id", "") or "")
        channel_id = str(getattr(source, "parent_chat_id", "") or getattr(source, "chat_id", "") or "")
        guild_dir = discord_root() / "guilds" / (guild_id or "direct")
        channel_dir = child_by_id(guild_dir / "channels", channel_id)
        if channel_dir is None:
            return ""
        path = channel_dir / "channel.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return str(data.get("channel_name") or "").strip()
    except Exception:
        return ""


def _auto_binding_allowed(source: Any) -> bool:
    # Keep automatic inference narrow: the user's student threads live in 수시
    # channels.  Manual /student-binding works anywhere.
    channel_name = _workspace_channel_name(source)
    return "수시" in channel_name


def _read(scope_key: str) -> dict[str, Any] | None:
    if not scope_key:
        return None
    db = _get_db_path()
    _ensure_schema(db)
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT payload, updated_at FROM student_thread_binding WHERE scope_key = ?",
            (scope_key,),
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload"])
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if isinstance(payload, dict):
        payload["updated_at"] = row["updated_at"]
        return payload
    return None


def _write(scope_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    db = _get_db_path()
    _ensure_schema(db)
    record = {**payload, "scope_key": scope_key}
    updated_at = _now()
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO student_thread_binding (scope_key, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(scope_key) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (scope_key, json.dumps(record, ensure_ascii=False), updated_at),
        )
    record["updated_at"] = updated_at
    return record


def save_manual_binding(source: Any, student_name: str) -> dict[str, Any]:
    scope_key = thread_binding_scope_key_from_source(source)
    if not scope_key:
        raise ValueError("student binding works only inside a Discord thread")
    clean_name = normalize_student_name(student_name)
    if not clean_name:
        raise ValueError("student name is required")
    return _write(
        scope_key,
        {
            "kind": "student_thread_binding",
            "source": "manual",
            "student_query": clean_name,
            "thread_name": thread_name_from_source(source),
            "confirmed": True,
        },
    )


def clear_binding(source: Any) -> dict[str, Any]:
    scope_key = thread_binding_scope_key_from_source(source)
    if not scope_key:
        raise ValueError("student binding works only inside a Discord thread")
    return _write(
        scope_key,
        {
            "kind": "student_thread_binding",
            "source": _CLEARED_SOURCE,
            "student_query": "",
            "thread_name": thread_name_from_source(source),
            "confirmed": False,
        },
    )


def refresh_inferred_binding(source: Any) -> dict[str, Any] | None:
    scope_key = thread_binding_scope_key_from_source(source)
    if not scope_key:
        return None
    name = thread_name_from_source(source)
    if not looks_like_student_thread_name(name) or not _auto_binding_allowed(source):
        return None
    return _write(
        scope_key,
        {
            "kind": "student_thread_binding",
            "source": "thread_name",
            "student_query": name,
            "thread_name": name,
            "confirmed": False,
        },
    )


def get_binding_for_source(source: Any, *, infer: bool = True) -> dict[str, Any]:
    scope_key = thread_binding_scope_key_from_source(source)
    if not scope_key:
        return {}
    existing = _read(scope_key)
    if existing:
        if existing.get("source") == _CLEARED_SOURCE:
            return {}
        return existing
    if not infer:
        return {}
    inferred = refresh_inferred_binding(source)
    return inferred or {}


def clear_bindings_for_thread(source: Any) -> int:
    scope_key = thread_binding_scope_key_from_source(source)
    if not scope_key:
        return 0
    db = _get_db_path()
    _ensure_schema(db)
    with sqlite3.connect(db) as conn:
        cur = conn.execute("DELETE FROM student_thread_binding WHERE scope_key = ?", (scope_key,))
        return int(cur.rowcount or 0)


def format_binding_prompt_note(binding: dict[str, Any]) -> str:
    student = str(binding.get("student_query") or "").strip()
    if not student:
        return ""
    source = str(binding.get("source") or "").strip()
    confidence = "수동 확정" if source == "manual" else "스레드명 추론"
    return (
        f"이 Discord 스레드는 학생 '{student}' 전용 상담/자료 스레드로 바인딩되어 있어({confidence}). "
        "이번 사용자 메시지에 다른 학생 이름이 명시되지 않았다면 이 학생을 기본 student_query로 사용해. "
        "다른 학생이 명시되면 그 턴만 명시 학생을 우선하고, 전화번호·결제·민감 메모 같은 보호 정보는 노출하지 마."
    )


def format_binding_status(binding: dict[str, Any]) -> str:
    if not binding:
        return "이 스레드에는 아직 학생 바인딩이 없어. `/student-binding 홍길동`처럼 묶을 수 있어."
    student = str(binding.get("student_query") or "").strip()
    source = str(binding.get("source") or "").strip()
    source_label = "수동 바인딩" if source == "manual" else "스레드명 자동 추론"
    return f"현재 이 스레드 기본 학생은 **{student}**이야. ({source_label})"


def student_binding_command(raw_args: str = "") -> str:
    from .context import current_event_context

    event = current_event_context()
    source = getattr(event, "source", None)
    if source is None or not getattr(source, "thread_id", None):
        return "학생 바인딩은 Discord 스레드 안에서만 사용할 수 있어."
    args = str(raw_args or "").strip()
    if not args or args in {"확인", "status", "check"}:
        return format_binding_status(get_binding_for_source(source, infer=True))
    lowered = args.lower()
    if lowered in {"해제", "clear", "reset", "unbind"}:
        clear_binding(source)
        return "이 스레드의 학생 자동 바인딩을 해제했어. 스레드명 자동 추론도 다시 쓰지 않게 막아둘게."
    if lowered in {"새로고침", "refresh", "infer"}:
        binding = refresh_inferred_binding(source)
        if not binding:
            return "스레드명/채널명 기준으로 자동 바인딩할 학생을 안전하게 확정하지 못했어. `/student-binding 학생이름`으로 직접 묶어줘."
        return format_binding_status(binding)
    for prefix in ("변경 ", "bind ", "set ", "학생 "):
        if lowered.startswith(prefix.strip().lower() + " "):
            args = args[len(prefix):].strip()
            break
    binding = save_manual_binding(source, args)
    return format_binding_status(binding)
