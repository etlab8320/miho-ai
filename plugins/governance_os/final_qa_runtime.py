"""Runtime bridge between Final Delivery Gate and Final QA Repair."""

from __future__ import annotations

from typing import Any

from .delivery_safety import contains_internal_guard_leak


def repair_blocked_answer(
    *,
    user_text: str,
    response_text: str,
    decision: Any,
    context: dict[str, Any],
) -> str:
    if not _runtime_repair_enabled(context):
        return ""
    try:
        from .final_qa import repair_answer_until_pass

        repaired = repair_answer_until_pass(
            user_text,
            response_text,
            evidence={
                "reason": str(getattr(decision, "reason", "")),
                "playbook_key": str(getattr(decision, "playbook_key", "")),
                "retry_tools": list(getattr(decision, "retry_tools", ())),
            },
        )
    except Exception:
        return ""
    repaired = str(repaired or "").strip()
    if not repaired or repaired == response_text:
        return ""
    if contains_internal_guard_leak(repaired):
        return ""
    return repaired


def _runtime_repair_enabled(context: dict[str, Any]) -> bool:
    platform = str(context.get("platform") or "").strip()
    session_id = str(context.get("session_id") or "").strip()
    return bool(platform or session_id)
