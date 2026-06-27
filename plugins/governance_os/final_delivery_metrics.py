"""Telemetry helpers for Final Delivery recovery paths."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def monotonic_ms() -> int:
    return int(time.monotonic() * 1000)


def elapsed_ms(start_ms: int) -> int:
    return max(0, monotonic_ms() - int(start_ms or 0))


def record_delivery_recovery_metric(
    *,
    evidence: dict[str, Any],
    stage: str,
    status: str,
    task: str = "",
    duration_ms: int = 0,
    error: str = "",
    record_failure: Callable[..., dict[str, Any]] | None = None,
) -> None:
    """Record agent transport failures for Self-Harness mining."""

    clean_status = str(status or "").strip()
    if clean_status not in {"timeout", "error", "unavailable", "invalid"}:
        return
    decision = evidence.get("decision") if isinstance(evidence, dict) else {}
    if not isinstance(decision, dict):
        decision = {}
    playbook_key = str(decision.get("playbook_key") or evidence.get("playbook_key") or "unknown")
    retry_tools = decision.get("retry_tools") or evidence.get("retry_tools")
    tools_used = tuple(str(tool) for tool in retry_tools) if isinstance(retry_tools, list) else ()
    recorder = record_failure or _default_quality_failure_recorder
    try:
        recorder(
            request_id=str(evidence.get("session_id") or "final_delivery_recovery"),
            playbook_key=playbook_key,
            failure_signature=f"final_delivery_{stage}_{clean_status}",
            user_feedback=_metric_feedback(
                stage=stage,
                status=clean_status,
                task=task,
                duration_ms=duration_ms,
                error=error,
            ),
            tools_used=tools_used,
            duration_ms=int(duration_ms or 0),
            agent_chain=("final_delivery_orchestrator", stage),
        )
    except Exception as exc:
        logger.debug("failed to record final delivery recovery metric: %s", exc)


def _metric_feedback(
    *,
    stage: str,
    status: str,
    task: str,
    duration_ms: int,
    error: str,
) -> str:
    parts = [
        f"stage={stage}",
        f"status={status}",
        f"duration_ms={int(duration_ms or 0)}",
    ]
    if task:
        parts.append(f"task={task}")
    if error:
        parts.append(f"error={error[:160]}")
    return "Final Delivery recovery telemetry: " + " ".join(parts)


def _default_quality_failure_recorder(**kwargs: Any) -> dict[str, Any]:
    from .feedback_events import record_quality_failure

    return record_quality_failure(**kwargs)
