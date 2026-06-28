"""Self-Harness autopilot cron status with latest run evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .self_harness_cron import CRON_JOB_NAME


def build_autopilot_status() -> dict[str, Any]:
    try:
        from cron.jobs import OUTPUT_DIR, list_jobs

        jobs = list_jobs(include_disabled=True)
    except Exception as exc:
        return {
            "registered": False,
            "enabled": False,
            "ready": False,
            "progress_state": "cron_unavailable",
            "error": str(exc),
        }
    for job in jobs:
        if str(job.get("name") or "") == CRON_JOB_NAME:
            return _job_status(job, Path(OUTPUT_DIR))
    return {
        "registered": False,
        "enabled": False,
        "ready": False,
        "progress_state": "not_registered",
    }


def _job_status(job: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    receipt = _latest_receipt(output_dir, str(job.get("id") or ""))
    summary = _receipt_summary(receipt)
    payload = {
        "registered": True,
        "enabled": bool(job.get("enabled", True)),
        "schedule": _schedule_text(job),
        "next_run_at": str(job.get("next_run_at") or ""),
        "last_run_at": str(job.get("last_run_at") or ""),
        "last_status": str(job.get("last_status") or ""),
        "last_error": str(job.get("last_error") or ""),
        "last_delivery_error": str(job.get("last_delivery_error") or ""),
        "last_receipt": summary,
    }
    state = _progress_state(payload)
    payload["progress_state"] = state
    payload["ready"] = _ready(payload, state)
    return payload


def _schedule_text(job: dict[str, Any]) -> str:
    display = str(job.get("schedule_display") or "").strip()
    if display:
        return display
    schedule = job.get("schedule")
    if isinstance(schedule, dict):
        return str(schedule.get("display") or schedule.get("expr") or schedule.get("value") or "")
    return str(schedule or "")


def _latest_receipt(output_dir: Path, job_id: str) -> dict[str, Any]:
    if not job_id:
        return {}
    job_dir = output_dir / job_id
    try:
        latest = max(job_dir.glob("*.md"), key=lambda path: path.stat().st_mtime)
    except (OSError, ValueError):
        return {}
    try:
        return _parse_receipt(latest.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {}


def _parse_receipt(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        return {}
    try:
        payload = json.loads(text[start:])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _receipt_summary(receipt: dict[str, Any]) -> dict[str, Any]:
    activated = _items(receipt.get("activated"))
    rolled_back = _items(receipt.get("rolled_back"))
    held = _items(receipt.get("held"))
    skipped = _items(receipt.get("skipped_unsafe"))
    errors = _items(receipt.get("errors"))
    return {
        "present": bool(receipt),
        "candidate_count": _int(receipt.get("candidate_count")),
        "activated_count": len(activated),
        "rolled_back_count": len(rolled_back),
        "held_count": len(held),
        "skipped_unsafe_count": len(skipped),
        "error_count": len(errors),
        "held_reasons": _reasons(held),
        "error_reasons": _reasons(errors),
    }


def _progress_state(payload: dict[str, Any]) -> str:
    if not payload.get("enabled"):
        return "disabled"
    if not payload.get("last_run_at"):
        return "never_ran"
    if payload.get("last_status") != "ok":
        return "last_run_failed"
    receipt = payload.get("last_receipt") if isinstance(payload.get("last_receipt"), dict) else {}
    if not receipt or not receipt.get("present"):
        return "no_run_receipt"
    if int(receipt.get("error_count") or 0) > 0:
        return "run_errors"
    if int(receipt.get("activated_count") or 0) or int(receipt.get("rolled_back_count") or 0):
        return "validated_activity"
    if int(receipt.get("candidate_count") or 0) == 0:
        return "idle_no_candidates"
    if int(receipt.get("held_count") or 0) or int(receipt.get("skipped_unsafe_count") or 0):
        return "attention_needed"
    return "ok"


def _ready(payload: dict[str, Any], state: str) -> bool:
    return bool(
        payload.get("registered")
        and payload.get("enabled")
        and payload.get("last_status") == "ok"
        and state in {"validated_activity", "idle_no_candidates", "ok"}
    )


def _items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _reasons(items: list[dict[str, Any]]) -> list[str]:
    reasons = []
    for item in items:
        reason = str(item.get("reason") or item.get("error") or "").strip()
        if reason and reason not in reasons:
            reasons.append(reason)
    return reasons


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
