"""Owner profile storage for Miho's long-running user narrative.

This store is intentionally separate from USER.md:
- USER.md stays compact and prompt-friendly.
- MASTER_PROFILE.md keeps the richer owner narrative.
- timeline.db accumulates dated profile events like an autobiography log.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home
from utils import atomic_replace

# Safety cap so a runaway writer (buggy loop / promote spam) can't grow
# timeline.db without bound. Generous by default — normal use adds a handful of
# events per day — and overridable for special cases. Oldest events drop first.
_DEFAULT_TIMELINE_MAX_EVENTS = 20000


def _timeline_max_events() -> int:
    raw = os.getenv("MIHO_OWNER_TIMELINE_MAX_EVENTS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return _DEFAULT_TIMELINE_MAX_EVENTS

OWNER_PROFILE_DIRNAME = "owner_profile"
MASTER_PROFILE_FILENAME = "MASTER_PROFILE.md"
TIMELINE_DB_FILENAME = "timeline.db"
DAILY_SUMMARY_JOB_NAME = "owner-profile-daily-summary"

_BLOCKED_PATTERNS = (
    "ignore previous instructions",
    "disregard your instructions",
    "system prompt override",
    "authorized_keys",
    "~/.ssh",
    ".env",
)


def get_owner_profile_dir() -> Path:
    """Return the profile-scoped owner profile directory."""
    return get_miho_home() / "memories" / OWNER_PROFILE_DIRNAME


def get_master_profile_path() -> Path:
    """Return the master owner profile Markdown path."""
    return get_owner_profile_dir() / MASTER_PROFILE_FILENAME


def get_timeline_db_path() -> Path:
    """Return the owner profile timeline SQLite path."""
    return get_owner_profile_dir() / TIMELINE_DB_FILENAME


def ensure_owner_profile_store() -> Path:
    """Create owner profile storage and database schema if missing."""
    profile_dir = get_owner_profile_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(get_timeline_db_path()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profile_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_profile_events_created "
            "ON profile_events(created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_profile_events_category "
            "ON profile_events(category)"
        )
    return profile_dir


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _scan_content(content: str) -> str | None:
    lowered = content.lower()
    for pattern in _BLOCKED_PATTERNS:
        if pattern in lowered:
            return f"Blocked owner profile content: unsafe pattern '{pattern}'."
    return None


def read_master_profile(max_chars: int | None = None) -> str:
    """Read MASTER_PROFILE.md, optionally bounded for tool responses."""
    ensure_owner_profile_store()
    path = get_master_profile_path()
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8").strip()
    if max_chars and len(content) > max_chars:
        kept = max_chars // 2
        return (
            content[:kept]
            + f"\n\n[...truncated owner profile: {len(content)} chars total...]\n\n"
            + content[-kept:]
        )
    return content


def replace_master_profile(content: str, source: str = "owner_profile") -> dict[str, Any]:
    """Replace the master owner profile document."""
    content = content.strip()
    if not content:
        return {"success": False, "error": "content cannot be empty"}
    scan_error = _scan_content(content)
    if scan_error:
        return {"success": False, "error": scan_error}

    ensure_owner_profile_store()
    path = get_master_profile_path()
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content + "\n", encoding="utf-8")
    atomic_replace(str(tmp_path), path)
    append_profile_event(
        category="master_profile",
        title="Master profile replaced",
        content="MASTER_PROFILE.md was replaced.",
        source=source,
    )
    return {"success": True, "path": str(path), "chars": len(content)}


def append_to_master_profile(
    title: str,
    content: str,
    source: str = "owner_profile",
) -> dict[str, Any]:
    """Append a dated section to MASTER_PROFILE.md and timeline.db."""
    title = (title or "Profile update").strip()
    content = content.strip()
    if not content:
        return {"success": False, "error": "content cannot be empty"}
    scan_error = _scan_content(content)
    if scan_error:
        return {"success": False, "error": scan_error}

    ensure_owner_profile_store()
    path = get_master_profile_path()
    current = (
        path.read_text(encoding="utf-8").rstrip()
        if path.exists()
        else "# Owner Master Profile"
    )
    stamp = _now_iso()
    section = f"\n\n## {title}\n\n- Updated at: {stamp}\n- Source: {source}\n\n{content}\n"
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(current + section, encoding="utf-8")
    atomic_replace(str(tmp_path), path)
    append_profile_event(category="master_profile", title=title, content=content, source=source)
    return {"success": True, "path": str(path), "title": title}


def append_profile_event(
    category: str,
    title: str,
    content: str,
    source: str = "owner_profile",
) -> dict[str, Any]:
    """Append a dated owner profile event to timeline.db."""
    category = (category or "general").strip().lower().replace(" ", "_")
    title = (title or "Profile event").strip()
    content = content.strip()
    if not content:
        return {"success": False, "error": "content cannot be empty"}
    scan_error = _scan_content(content)
    if scan_error:
        return {"success": False, "error": scan_error}

    ensure_owner_profile_store()
    with sqlite3.connect(get_timeline_db_path()) as conn:
        cursor = conn.execute(
            """
            INSERT INTO profile_events(created_at, category, title, content, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (_now_iso(), category, title, content, source),
        )
        event_id = int(cursor.lastrowid)
        _prune_timeline(conn, _timeline_max_events())
    return {"success": True, "id": event_id, "category": category, "title": title}


def _prune_timeline(conn: sqlite3.Connection, max_events: int) -> None:
    """Drop oldest events beyond max_events to bound timeline.db growth."""
    if max_events <= 0:
        return
    conn.execute(
        """
        DELETE FROM profile_events
        WHERE id NOT IN (
            SELECT id FROM profile_events
            ORDER BY created_at DESC, id DESC
            LIMIT ?
        )
        """,
        (max_events,),
    )


def list_profile_events(limit: int = 20, category: str | None = None) -> list[dict[str, Any]]:
    """Return recent owner profile events."""
    ensure_owner_profile_store()
    safe_limit = max(1, min(int(limit or 20), 100))
    params: list[Any] = []
    where = ""
    if category:
        where = "WHERE category = ?"
        params.append(category.strip().lower().replace(" ", "_"))
    params.append(safe_limit)
    with sqlite3.connect(get_timeline_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, created_at, category, title, content, source
            FROM profile_events
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def search_profile_events(
    terms: list[str], limit: int = 40, category: str | None = None
) -> list[dict[str, Any]]:
    """Return events whose title/content contains any term (recent first).

    Lets relevant older owner memories surface even when they fall outside the
    most-recent window list_profile_events returns, so recall isn't capped at
    the latest N events. Terms are matched as case-insensitive substrings.
    """
    cleaned = [t.strip() for t in (terms or []) if t and t.strip()]
    if not cleaned:
        return []
    ensure_owner_profile_store()
    safe_limit = max(1, min(int(limit or 40), 200))
    clauses: list[str] = []
    params: list[Any] = []
    for term in cleaned:
        clauses.append("(LOWER(title) LIKE ? OR LOWER(content) LIKE ?)")
        like = f"%{term.lower()}%"
        params.extend([like, like])
    where = "(" + " OR ".join(clauses) + ")"
    if category:
        where += " AND category = ?"
        params.append(category.strip().lower().replace(" ", "_"))
    params.append(safe_limit)
    with sqlite3.connect(get_timeline_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT id, created_at, category, title, content, source
            FROM profile_events
            WHERE {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def build_daily_summary_prompt() -> str:
    """Return the scheduled prompt that writes an owner profile day summary."""
    return (
        "Summarize today's durable owner context and save it with "
        "owner_profile(action='append_event', category='daily_summary').\n\n"
        "Use session_search if available to recall today's conversations. "
        "Focus only on durable context about the owner, not transient tool logs.\n\n"
        "Write a concise Korean summary with these labels when evidence exists:\n"
        "- 오늘 한 작업\n"
        "- 하려고 한 일\n"
        "- 관심사\n"
        "- 상태/감정/상황\n"
        "- 내일 이어갈 힌트\n\n"
        "If there is no meaningful owner context today, do not invent details. "
        "Either write a very short 'no significant owner profile update' event, "
        "or respond with exactly [SILENT]."
    )


def ensure_daily_summary_job(schedule: str = "0 23 * * *") -> dict[str, Any]:
    """Ensure the profile has a recurring 23:00 owner profile summary cron job."""
    from cron.jobs import compute_next_run, create_job, load_jobs, parse_schedule, save_jobs

    ensure_owner_profile_store()
    prompt = build_daily_summary_prompt()
    toolsets = ["memory", "session_search", "cronjob"]
    jobs = load_jobs()
    for job in jobs:
        if job.get("name") == DAILY_SUMMARY_JOB_NAME:
            changed = False
            if job.get("prompt") != prompt:
                job["prompt"] = prompt
                changed = True
            if job.get("enabled_toolsets") != toolsets:
                job["enabled_toolsets"] = toolsets
                changed = True
            if job.get("deliver") != "local":
                job["deliver"] = "local"
                changed = True
            current_schedule = job.get("schedule", {}).get("expr")
            if current_schedule != schedule:
                parsed = parse_schedule(schedule)
                job["schedule"] = parsed
                job["schedule_display"] = parsed.get("display", schedule)
                job["next_run_at"] = compute_next_run(parsed)
                changed = True
            if changed:
                save_jobs(jobs)
            return {"success": True, "created": False, "updated": changed, "job": job}

    job = create_job(
        prompt=prompt,
        schedule=schedule,
        name=DAILY_SUMMARY_JOB_NAME,
        deliver="local",
        enabled_toolsets=toolsets,
    )
    return {"success": True, "created": True, "updated": False, "job": job}
