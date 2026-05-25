"""Gateway-facing Discord workspace memory operations."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from gateway.config import Platform
from gateway.discord_workspace import ensure_workspace
from gateway.discord_workspace_vectors import index_rag_record, retrieve_rag_context
from gateway.session import SessionSource
from miho_cli.owner_profile import append_profile_event


def _workspace_for_source(source: SessionSource):
    return ensure_workspace(
        guild_id=getattr(source, "guild_id", None),
        channel_id=getattr(source, "parent_chat_id", None) or source.chat_id,
        channel_name=getattr(source, "chat_name", None),
        thread_id=getattr(source, "thread_id", None),
        thread_name=getattr(source, "chat_name", None) if getattr(source, "thread_id", None) else None,
    )


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())
    except OSError:
        return 0


def _read_messages(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _format_scope(workspace) -> str:
    if workspace.thread_dir:
        return "thread"
    return "channel"


def memory_status(source: SessionSource) -> str:
    if source.platform != Platform.DISCORD:
        return "이 기억 명령은 Discord 채널/스레드에서만 쓸 수 있어."
    workspace = _workspace_for_source(source)
    rag_dir = workspace.rag_dir
    messages = _count_jsonl(rag_dir / "messages.jsonl")
    vectors = _count_jsonl(rag_dir / "vectors.jsonl")
    parent_messages = _count_jsonl(workspace.channel_rag_dir / "messages.jsonl")
    lines = [
        "Miho Discord memory",
        f"- Scope: {_format_scope(workspace)}",
        f"- Messages: {messages}",
        f"- Vectors: {vectors}",
        f"- Parent channel messages: {parent_messages}",
        f"- Path: {workspace.active_dir}",
    ]
    return "\n".join(lines)


def memory_search(source: SessionSource, query: str, *, limit: int = 5) -> str:
    if source.platform != Platform.DISCORD:
        return "이 기억 검색은 Discord 채널/스레드에서만 쓸 수 있어."
    query = query.strip()
    if not query:
        return "사용법: `/memory search 검색어`"
    workspace = _workspace_for_source(source)
    matches = retrieve_rag_context(workspace.rag_dir, query, limit=limit)
    if not matches:
        return "관련 기억을 찾지 못했어."
    lines = [f"Miho memory search: {query}"]
    for idx, item in enumerate(matches, start=1):
        text = str(item.get("text") or "").replace("\n", " ").strip()
        if len(text) > 220:
            text = text[:217] + "..."
        score = float(item.get("score") or 0)
        user = str(item.get("user_name") or item.get("role") or "memory")
        lines.append(f"{idx}. {user} · {score:.2f} · {text}")
    return "\n".join(lines)


def memory_rebuild(source: SessionSource) -> str:
    if source.platform != Platform.DISCORD:
        return "이 기억 재색인은 Discord 채널/스레드에서만 쓸 수 있어."
    workspace = _workspace_for_source(source)
    rag_dir = workspace.rag_dir
    messages = _read_messages(rag_dir / "messages.jsonl")
    vector_path = rag_dir / "vectors.jsonl"
    index_path = rag_dir / "vector_index.json"
    for path in (vector_path, index_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    for record in messages:
        index_rag_record(rag_dir, record)
    return f"기억 재색인 완료: {len(messages)}개 메시지"


def _profile_source(source: SessionSource) -> str:
    guild = getattr(source, "guild_id", "") or "direct"
    channel = getattr(source, "parent_chat_id", None) or source.chat_id
    thread = getattr(source, "thread_id", None)
    if thread:
        return f"discord:guild/{guild}/channel/{channel}/thread/{thread}"
    return f"discord:guild/{guild}/channel/{channel}"


def memory_promote(source: SessionSource, content: str) -> str:
    if source.platform != Platform.DISCORD:
        return "이 기억 승격은 Discord 채널/스레드에서만 쓸 수 있어."
    content = content.strip()
    if not content:
        return "사용법: `/memory promote 오래 남길 사실이나 결정`"
    result = append_profile_event(
        category="discord_memory",
        title=str(getattr(source, "chat_name", None) or "Discord memory"),
        content=content,
        source=_profile_source(source),
    )
    if not result.get("success"):
        return f"장기기억 저장 실패: {result.get('error') or 'unknown error'}"
    return "장기기억으로 승격했어. 필요할 때 owner_profile 타임라인에서 다시 꺼낼 수 있어."


def run_memory_command(source: SessionSource, raw_args: str) -> str:
    try:
        tokens = shlex.split(raw_args or "")
    except ValueError:
        return "명령을 읽지 못했어. 따옴표를 확인해줘."
    action = tokens[0].lower() if tokens else "status"
    rest = " ".join(tokens[1:]).strip()
    if action in {"status", "stat", "상태"}:
        return memory_status(source)
    if action in {"search", "find", "검색"}:
        return memory_search(source, rest)
    if action in {"rebuild", "reindex", "재색인"}:
        return memory_rebuild(source)
    if action in {"promote", "pin", "승격", "고정"}:
        return memory_promote(source, rest)
    return "사용법: `/memory status`, `/memory search 검색어`, `/memory rebuild`, `/memory promote 내용`"
