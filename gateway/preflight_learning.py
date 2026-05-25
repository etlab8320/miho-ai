"""Local review queue for gateway preflight false positives."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home


_CONVERSATION_CORRECTION_RE = re.compile(
    r"(?:"
    r"(?:아니|ㄴㄴ|노|no|not)\s*(?:이거|그거|그냥)?\s*(?:대화|잡담|질문|얘기)"
    r"|(?:대화|잡담|질문|얘기)\s*(?:야|이야|임|입니다|였어|였는데)"
    r"|(?:just|only)\s+(?:chat|conversation|question)"
    r")",
    re.IGNORECASE,
)


def review_queue_path(home: Path | None = None) -> Path:
    """Return the local JSONL review queue path."""
    root = Path(home) if home is not None else get_miho_home()
    return root / "review" / "preflight_false_positives.jsonl"


def is_conversation_correction(text: str | None) -> bool:
    """Return True when the user says the preflight prompt was for chat only."""
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return False
    return bool(_CONVERSATION_CORRECTION_RE.search(raw))


def remember_preflight_prompt(
    pending: dict[str, dict[str, Any]],
    session_key: str,
    *,
    original_text: str | None,
    question: str,
    platform: str | None = None,
) -> None:
    """Remember the last preflight prompt so a correction can be reviewed."""
    if not session_key:
        return
    pending[session_key] = {
        "original_text": str(original_text or "")[:2000],
        "question": question,
        "platform": platform or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def record_false_positive(
    pending_entry: dict[str, Any],
    *,
    session_key: str,
    correction_text: str | None,
    home: Path | None = None,
) -> Path:
    """Append a false-positive review item to the local JSONL queue."""
    path = review_queue_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from agent.redact import redact_sensitive_text

        original_text = redact_sensitive_text(str(pending_entry.get("original_text") or ""))
        correction = redact_sensitive_text(str(correction_text or ""))
    except Exception:
        original_text = str(pending_entry.get("original_text") or "")
        correction = str(correction_text or "")

    record = {
        "kind": "forge_preflight_false_positive",
        "session_key": session_key,
        "platform": pending_entry.get("platform") or "",
        "original_text": original_text[:2000],
        "correction_text": correction[:1000],
        "question": str(pending_entry.get("question") or "")[:1000],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def consume_preflight_correction(
    pending: dict[str, dict[str, Any]],
    session_key: str,
    *,
    correction_text: str | None,
    home: Path | None = None,
) -> bool:
    """Record and clear a pending preflight item when the user corrects it."""
    if not session_key or not is_conversation_correction(correction_text):
        return False
    pending_entry = pending.pop(session_key, None)
    if not pending_entry:
        return False
    record_false_positive(
        pending_entry,
        session_key=session_key,
        correction_text=correction_text,
        home=home,
    )
    return True
