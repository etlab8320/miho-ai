"""Durable ledger and rollback primitives for Miho Evolution OS."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from miho_constants import get_miho_home

logger = logging.getLogger(__name__)


EVENTS_FILENAME = "events.jsonl"
HARNESS_RULES_FILENAME = "harness_rules.json"
VALID_EVENT_KINDS = frozenset(
    {
        "proposal",
        "promotion",
        "rollback",
        "snapshot",
        "failure_pattern",
        "harness_rule",
        "note",
    }
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def evolution_dir() -> Path:
    return get_miho_home() / "evolution"


def events_path() -> Path:
    return evolution_dir() / EVENTS_FILENAME


def harness_rules_path() -> Path:
    return evolution_dir() / HARNESS_RULES_FILENAME


def ensure_store() -> Path:
    root = evolution_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = events_path()
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return root


def _next_event_id() -> int:
    events = list_events(limit=None)
    if not events:
        return 1
    return max(int(e.get("id") or 0) for e in events) + 1


def _safe_jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _safe_jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [_safe_jsonable(v) for v in value]
        return str(value)


def record_event(
    *,
    kind: str,
    title: str,
    summary: str = "",
    evidence: str = "",
    changed_files: Optional[Iterable[str]] = None,
    snapshot_id: Optional[str] = None,
    proposal_id: Optional[int] = None,
    status: str = "recorded",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Append one evolution event to the JSONL ledger."""
    normalized_kind = (kind or "").strip().lower()
    if normalized_kind not in VALID_EVENT_KINDS:
        allowed = ", ".join(sorted(VALID_EVENT_KINDS))
        raise ValueError(f"kind must be one of: {allowed}")
    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")

    ensure_store()
    event = {
        "id": _next_event_id(),
        "created_at": _now_iso(),
        "kind": normalized_kind,
        "status": (status or "recorded").strip() or "recorded",
        "title": title,
        "summary": (summary or "").strip(),
        "evidence": (evidence or "").strip(),
        "changed_files": [str(p) for p in (changed_files or [])],
        "snapshot_id": snapshot_id,
        "proposal_id": proposal_id,
        "metadata": _safe_jsonable(metadata or {}),
    }
    with events_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return event


def list_events(*, limit: Optional[int] = 20, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return evolution events newest-first by default."""
    path = events_path()
    if not path.exists():
        return []
    events: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("Skipping corrupt evolution ledger line: %r", line[:120])
                continue
            if kind and item.get("kind") != kind:
                continue
            events.append(item)
    events.sort(key=lambda e: (str(e.get("created_at") or ""), int(e.get("id") or 0)), reverse=True)
    if limit is None:
        return events
    return events[: max(0, int(limit))]


def get_event(event_id: int) -> Optional[Dict[str, Any]]:
    for event in list_events(limit=None):
        if int(event.get("id") or 0) == int(event_id):
            return event
    return None


def snapshot_skills(*, reason: str = "evolution-manual") -> Dict[str, Any]:
    """Take a skill tree snapshot and record it in the evolution ledger."""
    from agent import curator_backup

    snap = curator_backup.snapshot_skills(reason=reason)
    if snap is None:
        return {"success": False, "error": "snapshot failed or backups disabled"}
    event = record_event(
        kind="snapshot",
        title=f"Skill snapshot {snap.name}",
        summary=reason,
        snapshot_id=snap.name,
        metadata={"path": str(snap)},
    )
    return {"success": True, "snapshot_id": snap.name, "path": str(snap), "event": event}


def record_skill_mutation(
    *,
    action: str,
    skill_name: str,
    success: bool,
    changed_files: Optional[Iterable[str]] = None,
    snapshot_id: Optional[str] = None,
    message: str = "",
    error: str = "",
) -> Dict[str, Any]:
    """Record a skill_manage mutation as a promotion-style event."""
    status = "promoted" if success else "failed"
    return record_event(
        kind="promotion",
        title=f"skill_manage {action} {skill_name}",
        summary=message if success else error,
        changed_files=changed_files,
        snapshot_id=snapshot_id,
        status=status,
        metadata={"action": action, "skill": skill_name, "success": bool(success)},
    )


def snapshot_before_skill_mutation(*, action: str, skill_name: str) -> Optional[str]:
    """Create a pre-mutation skill snapshot for reversible skill evolution."""
    try:
        from agent import curator_backup

        snap = curator_backup.snapshot_skills(reason=f"pre-skill_manage:{action}:{skill_name}")
        return snap.name if snap is not None else None
    except Exception:
        logger.debug("Failed to create pre skill mutation snapshot", exc_info=True)
        return None


def list_harness_rules() -> List[Dict[str, Any]]:
    path = harness_rules_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rules = data.get("rules") if isinstance(data, dict) else data
    if not isinstance(rules, list):
        return []
    return [r for r in rules if isinstance(r, dict)]


def _write_harness_rules(rules: List[Dict[str, Any]]) -> None:
    ensure_store()
    payload = {"updated_at": _now_iso(), "rules": rules}
    fd, tmp = tempfile.mkstemp(dir=str(evolution_dir()), prefix=".harness_rules_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, harness_rules_path())
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def rollback_event(event_id: int) -> Tuple[bool, str, Dict[str, Any]]:
    """Rollback using the snapshot or harness rule attached to an evolution event."""
    event = get_event(event_id)
    if not event:
        return False, f"evolution event {event_id} not found", {}

    if event.get("kind") == "harness_rule":
        return _rollback_harness_rule(event_id, event)

    snapshot_id = event.get("snapshot_id")
    if not snapshot_id:
        return False, f"evolution event {event_id} has no snapshot_id", {"event": event}

    from agent import curator_backup

    ok, msg, safety_snapshot = curator_backup.rollback(backup_id=str(snapshot_id))
    rollback = record_event(
        kind="rollback",
        title=f"rollback evolution event {event_id}",
        summary=msg,
        snapshot_id=str(snapshot_id),
        proposal_id=event_id,
        status="rolled_back" if ok else "failed",
        metadata={
            "target_event": event,
            "safety_snapshot": str(safety_snapshot) if safety_snapshot else None,
        },
    )
    data: Dict[str, Any] = {
        "safety_snapshot": str(safety_snapshot) if safety_snapshot else None,
        "rollback_event": rollback,
    }
    return ok, msg, data


def _rollback_harness_rule(event_id: int, event: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    rules = list_harness_rules()
    changed = False
    for rule in rules:
        if int(rule.get("event_id") or 0) == int(event_id):
            rule["status"] = "rolled_back"
            rule["rolled_back_at"] = _now_iso()
            changed = True
            break
    if not changed:
        return False, f"harness rule for evolution event {event_id} not found", {"event": event}
    _write_harness_rules(rules)
    rollback = record_event(
        kind="rollback",
        title=f"rollback harness rule event {event_id}",
        summary=f"deactivated harness rule from evolution event {event_id}",
        proposal_id=event_id,
        status="rolled_back",
        metadata={"target_event": event},
    )
    return True, f"deactivated harness rule from evolution event {event_id}", {"rollback_event": rollback}
