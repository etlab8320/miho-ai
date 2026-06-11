"""Vector record helpers for Discord workspace RAG."""

from __future__ import annotations

from typing import Any


def vector_record_text(record: dict[str, Any]) -> str:
    parts = [
        str(record.get("role") or ""),
        str(record.get("source_kind") or ""),
        str(record.get("user_name") or ""),
        str(record.get("event_type") or ""),
        str(record.get("text") or ""),
    ]
    return "\n".join(part for part in parts if part)


def vector_payload(record: dict[str, Any], *, fallback_id: str, method: str, vector: list[float]) -> dict[str, Any]:
    return {
        "id": record.get("message_id") or fallback_id,
        "timestamp": record.get("timestamp") or "",
        "date": record.get("date") or "",
        "timezone": record.get("timezone") or "",
        "role": record.get("role") or "",
        "source_kind": record.get("source_kind") or "",
        "user_id": record.get("user_id") or "",
        "user_name": record.get("user_name") or "",
        "event_type": record.get("event_type") or "",
        "thread_id": record.get("thread_id") or "",
        "thread_name": record.get("thread_name") or "",
        "text": record.get("text") or "",
        "embedding_method": method,
        "embedding": vector,
    }
