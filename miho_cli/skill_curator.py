"""Skill evolution candidate store for Miho.

The regular curator maintains existing agent-created skills. This module
captures the earlier signal: failed patterns, missing steps in existing skills,
and new reusable workflows that should become skills after review.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from miho_constants import get_miho_home

SKILL_CURATOR_DIRNAME = ".skill_curator"
SKILL_CURATOR_DB_FILENAME = "candidates.db"
DAILY_SKILL_REVIEW_JOB_NAME = "skill-curator-daily-review"

KINDS = frozenset({"new_skill", "update_existing", "failure_pattern"})
STATUSES = frozenset({"pending", "promoted", "dismissed"})
_EVIDENCE_LIMIT = 6000
_BLOCKED_PATTERNS = (
    "ignore previous instructions",
    "disregard your instructions",
    "system prompt override",
    "authorized_keys",
    "~/.ssh",
    ".env",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_skill_curator_dir() -> Path:
    return get_miho_home() / "skills" / SKILL_CURATOR_DIRNAME


def get_skill_curator_db_path() -> Path:
    return get_skill_curator_dir() / SKILL_CURATOR_DB_FILENAME


def ensure_skill_curator_store() -> Path:
    """Create the skill curator candidate database if needed."""
    root = get_skill_curator_dir()
    root.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(get_skill_curator_db_path()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS skill_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                title TEXT NOT NULL,
                summary TEXT NOT NULL,
                evidence TEXT NOT NULL,
                suggested_skill TEXT,
                target_skill TEXT,
                source TEXT NOT NULL,
                hits INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_skill_candidates_status "
            "ON skill_candidates(status, updated_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_skill_candidates_kind "
            "ON skill_candidates(kind, updated_at DESC)"
        )
    return root


def _scan_text(*values: str) -> str | None:
    lowered = "\n".join(v for v in values if v).lower()
    for pattern in _BLOCKED_PATTERNS:
        if pattern in lowered:
            return f"Blocked skill curator content: unsafe pattern '{pattern}'."
    return None


def _normalize_kind(kind: str) -> str:
    normalized = (kind or "").strip().lower()
    if normalized not in KINDS:
        allowed = ", ".join(sorted(KINDS))
        raise ValueError(f"kind must be one of: {allowed}")
    return normalized


def _normalize_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized not in STATUSES:
        allowed = ", ".join(sorted(STATUSES))
        raise ValueError(f"status must be one of: {allowed}")
    return normalized


def _bounded_evidence(existing: str, new: str) -> str:
    new = new.strip()
    if not existing:
        combined = new
    elif new and new not in existing:
        combined = f"{existing.rstrip()}\n\n---\n{new}"
    else:
        combined = existing
    if len(combined) <= _EVIDENCE_LIMIT:
        return combined
    return combined[-_EVIDENCE_LIMIT:].lstrip()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return dict(row)


def record_skill_candidate(
    *,
    kind: str,
    title: str,
    summary: str,
    evidence: str,
    suggested_skill: str | None = None,
    target_skill: str | None = None,
    source: str = "skill_curator",
) -> dict[str, Any]:
    """Record or reinforce a pending skill-evolution candidate."""
    normalized_kind = _normalize_kind(kind)
    title = (title or "").strip()
    summary = (summary or "").strip()
    evidence = (evidence or "").strip()
    suggested_skill = (suggested_skill or "").strip() or None
    target_skill = (target_skill or "").strip() or None
    source = (source or "skill_curator").strip()
    if not title or not summary or not evidence:
        return {"success": False, "error": "title, summary, and evidence are required"}
    scan_error = _scan_text(title, summary, evidence, suggested_skill or "", target_skill or "")
    if scan_error:
        return {"success": False, "error": scan_error}

    ensure_skill_curator_store()
    now = _now_iso()
    with sqlite3.connect(get_skill_curator_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM skill_candidates
            WHERE status = 'pending'
              AND kind = ?
              AND lower(title) = lower(?)
              AND coalesce(suggested_skill, '') = coalesce(?, '')
              AND coalesce(target_skill, '') = coalesce(?, '')
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (normalized_kind, title, suggested_skill, target_skill),
        ).fetchone()
        if row:
            updated_evidence = _bounded_evidence(str(row["evidence"]), evidence)
            conn.execute(
                """
                UPDATE skill_candidates
                SET updated_at = ?, summary = ?, evidence = ?, source = ?,
                    hits = hits + 1
                WHERE id = ?
                """,
                (now, summary, updated_evidence, source, int(row["id"])),
            )
            candidate_id = int(row["id"])
        else:
            cursor = conn.execute(
                """
                INSERT INTO skill_candidates(
                    created_at, updated_at, kind, status, title, summary,
                    evidence, suggested_skill, target_skill, source, hits
                )
                VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    now,
                    now,
                    normalized_kind,
                    title,
                    summary,
                    evidence,
                    suggested_skill,
                    target_skill,
                    source,
                ),
            )
            candidate_id = int(cursor.lastrowid)
        saved = conn.execute(
            "SELECT * FROM skill_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
    return {"success": True, "candidate": _row_to_dict(saved)}


def list_skill_candidates(
    *,
    status: str = "pending",
    kind: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """List skill candidates by status and optional kind."""
    normalized_status = _normalize_status(status)
    normalized_kind = _normalize_kind(kind) if kind else None
    safe_limit = max(1, min(int(limit or 20), 100))
    ensure_skill_curator_store()
    params: list[Any] = [normalized_status]
    where = "WHERE status = ?"
    if normalized_kind:
        where += " AND kind = ?"
        params.append(normalized_kind)
    params.append(safe_limit)
    with sqlite3.connect(get_skill_curator_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT * FROM skill_candidates
            {where}
            ORDER BY hits DESC, updated_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def update_skill_candidate(
    candidate_id: int,
    *,
    status: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Mark a candidate as promoted or dismissed."""
    normalized_status = _normalize_status(status)
    if normalized_status == "pending":
        return {"success": False, "error": "use promoted or dismissed for updates"}
    note = (note or "").strip()
    scan_error = _scan_text(note)
    if scan_error:
        return {"success": False, "error": scan_error}

    ensure_skill_curator_store()
    now = _now_iso()
    with sqlite3.connect(get_skill_curator_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM skill_candidates WHERE id = ?",
            (int(candidate_id),),
        ).fetchone()
        if not row:
            return {"success": False, "error": f"candidate {candidate_id} not found"}
        evidence = str(row["evidence"])
        if note:
            evidence = _bounded_evidence(evidence, f"[{normalized_status}] {note}")
        conn.execute(
            """
            UPDATE skill_candidates
            SET status = ?, updated_at = ?, evidence = ?
            WHERE id = ?
            """,
            (normalized_status, now, evidence, int(candidate_id)),
        )
        saved = conn.execute(
            "SELECT * FROM skill_candidates WHERE id = ?",
            (int(candidate_id),),
        ).fetchone()
    return {"success": True, "candidate": _row_to_dict(saved)}


def build_daily_skill_review_prompt() -> str:
    """Return the scheduled prompt for reviewing skill candidates."""
    return (
        "Review Miho's pending skill curator candidates.\n\n"
        "1. Call skill_curator(action='list_candidates', status='pending', limit=50).\n"
        "2. For failure_pattern candidates, identify the reusable lesson and decide "
        "whether an existing skill needs a patch or a new skill is justified.\n"
        "3. For update_existing candidates, inspect the target skill with skill_view "
        "and patch it with skill_manage only when the evidence is concrete.\n"
        "4. For new_skill candidates, create a skill only when the workflow is "
        "repeatable, tool-specific, and more useful than normal memory/RAG.\n"
        "5. After a real skill update/create, mark the candidate promoted with "
        "skill_curator(action='mark_promoted'). If it is too weak, mark dismissed "
        "with a short reason. Leave uncertain candidates pending.\n\n"
        "Do not invent evidence. Do not modify bundled or hub-installed skills "
        "unless skill_manage accepts the patch. Keep the final report concise."
    )


def ensure_daily_skill_review_job(schedule: str = "10 23 * * *") -> dict[str, Any]:
    """Ensure a recurring job reviews pending skill candidates."""
    from cron.jobs import compute_next_run, create_job, load_jobs, parse_schedule, save_jobs

    ensure_skill_curator_store()
    prompt = build_daily_skill_review_prompt()
    toolsets = ["skills", "session_search", "cronjob"]
    jobs = load_jobs()
    for job in jobs:
        if job.get("name") == DAILY_SKILL_REVIEW_JOB_NAME:
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
            if job.get("schedule", {}).get("expr") != schedule:
                parsed = parse_schedule(schedule)
                job["schedule"] = parsed
                job["schedule_display"] = parsed.get("display", schedule)
                job["next_run_at"] = compute_next_run(parsed)
                changed = True
            if changed:
                save_jobs(jobs)
            return {"success": True, "created": False, "job": job}

    job = create_job(
        prompt=prompt,
        schedule=schedule,
        name=DAILY_SKILL_REVIEW_JOB_NAME,
        deliver="local",
        enabled_toolsets=toolsets,
    )
    return {"success": True, "created": True, "job": job}
