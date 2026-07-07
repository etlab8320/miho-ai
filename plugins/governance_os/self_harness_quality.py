"""Long-horizon quality report for Governance OS Self-Harness."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class SelfHarnessQualityReport:
    ready: bool
    score: int
    status: str
    event_count: int
    failure_count: int
    timeout_failure_count: int
    rollback_signal_count: int
    historical_failure_count: int = 0
    baseline_created_at: str = ""
    reviewer_intervention_count: int = 0
    recurrent_failures: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    top_failures: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "score": self.score,
            "status": self.status,
            "event_count": self.event_count,
            "failure_count": self.failure_count,
            "timeout_failure_count": self.timeout_failure_count,
            "rollback_signal_count": self.rollback_signal_count,
            "historical_failure_count": self.historical_failure_count,
            "baseline_created_at": self.baseline_created_at,
            "reviewer_intervention_count": self.reviewer_intervention_count,
            "recurrent_failures": list(self.recurrent_failures),
            "top_failures": list(self.top_failures),
        }


def build_self_harness_quality_report(
    *,
    outcomes: list[dict[str, Any]] | None = None,
    limit: int = 200,
    min_recurrence: int = 2,
    baseline_created_at: str | None = None,
) -> SelfHarnessQualityReport:
    """Score whether Self-Harness is reducing repeated operational failures."""

    items = list(_default_outcomes(limit=limit) if outcomes is None else outcomes)
    baseline = (
        baseline_created_at
        if baseline_created_at is not None
        else (_default_baseline_created_at() if outcomes is None else "")
    )
    items, historical_items = _split_by_baseline(items, baseline)
    historical_failure_count = len(_failure_signatures(historical_items))
    raw_signatures = _failure_signatures(items)
    reviewer_intervention_count = _reviewer_intervention_count(items)
    signatures = _active_failure_signatures(items)
    counts = Counter(signatures)
    recurrent = _recurrent_failures(counts, min_recurrence=max(2, int(min_recurrence or 2)))
    timeout_count = sum(count for signature, count in counts.items() if "timeout" in signature)
    rollback_count = sum(count for signature, count in counts.items() if "rollback" in signature)
    failure_count = len(signatures)
    score = _quality_score(
        recurrent_count=len(recurrent),
        timeout_failure_count=timeout_count,
        rollback_signal_count=rollback_count,
        failure_count=failure_count,
    )
    ready = not recurrent and timeout_count == 0 and rollback_count == 0
    return SelfHarnessQualityReport(
        ready=ready,
        score=score,
        status=_status(
            event_count=len(items),
            failure_count=failure_count,
            recurrent_count=len(recurrent),
            timeout_failure_count=timeout_count,
            baseline_created_at=baseline,
            historical_failure_count=historical_failure_count,
            resolved_failure_count=max(0, len(raw_signatures) - len(signatures)),
        ),
        event_count=len(items),
        failure_count=failure_count,
        timeout_failure_count=timeout_count,
        rollback_signal_count=rollback_count,
        historical_failure_count=historical_failure_count,
        baseline_created_at=baseline,
        reviewer_intervention_count=reviewer_intervention_count,
        recurrent_failures=tuple(recurrent),
        top_failures=tuple(_top_failures(counts)),
    )


def _default_outcomes(*, limit: int) -> list[dict[str, Any]]:
    from .ledger import list_outcomes

    return list_outcomes(limit=max(1, int(limit or 1)))


def _default_baseline_created_at() -> str:
    try:
        from .versioning import active_registry_path

        payload = json.loads(active_registry_path().read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("activated_at") or "").strip()


def _split_by_baseline(
    outcomes: list[dict[str, Any]],
    baseline_created_at: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    baseline = _parse_datetime(baseline_created_at)
    if baseline is None:
        return outcomes, []
    current: list[dict[str, Any]] = []
    historical: list[dict[str, Any]] = []
    for outcome in outcomes:
        created_at = _outcome_created_at(outcome)
        if created_at is None or created_at >= baseline:
            current.append(outcome)
        else:
            historical.append(outcome)
    return current, historical


def _outcome_created_at(outcome: dict[str, Any]) -> datetime | None:
    for key in ("created_at", "event_created_at"):
        parsed = _parse_datetime(str(outcome.get(key) or ""))
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(value: str) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _failure_signatures(outcomes: list[dict[str, Any]]) -> list[str]:
    signatures: list[str] = []
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        failures = outcome.get("failures")
        if isinstance(failures, list):
                signatures.extend(str(item).strip() for item in failures if str(item).strip())
    return signatures


def _active_failure_signatures(outcomes: list[dict[str, Any]]) -> list[str]:
    open_by_playbook: dict[str, list[str]] = {}
    unscoped: list[str] = []
    for outcome in _chronological_outcomes(outcomes):
        playbook_key = str(outcome.get("playbook_key") or "").strip()
        failures = _outcome_failures(outcome)
        if playbook_key and not failures and _is_followup_pass(outcome):
            open_by_playbook.pop(playbook_key, None)
            continue
        if not failures:
            continue
        if not playbook_key:
            unscoped.extend(failures)
            continue
        open_by_playbook.setdefault(playbook_key, []).extend(failures)
    active = list(unscoped)
    for failures in open_by_playbook.values():
        active.extend(failures)
    return active


def _chronological_outcomes(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = [(index, outcome) for index, outcome in enumerate(outcomes) if isinstance(outcome, dict)]
    if not any(_outcome_created_at(outcome) is not None for _index, outcome in indexed):
        return [outcome for _index, outcome in indexed]
    return [
        outcome
        for _index, outcome in sorted(
            indexed,
            key=lambda item: (_outcome_created_at(item[1]) or datetime.min.replace(tzinfo=timezone.utc), item[0]),
        )
    ]


def _outcome_failures(outcome: dict[str, Any]) -> list[str]:
    failures = outcome.get("failures")
    if not isinstance(failures, list):
        return []
    review_status = str(outcome.get("review_status") or "").strip().lower()
    cleaned = [str(item).strip() for item in failures if str(item).strip()]
    if review_status == "retry_needed":
        # `reviewer_retry_needed` means the defense gate caught a weak first pass
        # and asked the agent to retry. Treat it as a reviewer intervention signal,
        # not an unresolved recurrent failure, unless a later event records a true
        # reviewer failure for the same playbook.
        cleaned = [item for item in cleaned if item != "reviewer_retry_needed"]
    return cleaned


def _reviewer_intervention_count(outcomes: list[dict[str, Any]]) -> int:
    count = 0
    for outcome in outcomes:
        if not isinstance(outcome, dict):
            continue
        review_status = str(outcome.get("review_status") or "").strip().lower()
        failures = outcome.get("failures")
        if review_status == "retry_needed" and isinstance(failures, list) and "reviewer_retry_needed" in failures:
            count += 1
    return count


def _is_followup_pass(outcome: dict[str, Any]) -> bool:
    return str(outcome.get("review_status") or "").strip().lower() == "pass"


def _recurrent_failures(counts: Counter[str], *, min_recurrence: int) -> list[dict[str, Any]]:
    return [
        {"signature": signature, "count": count}
        for signature, count in counts.most_common()
        if count >= min_recurrence
    ]


def _top_failures(counts: Counter[str], *, limit: int = 5) -> list[dict[str, Any]]:
    return [
        {"signature": signature, "count": count}
        for signature, count in counts.most_common(max(1, int(limit or 1)))
    ]


def _quality_score(
    *,
    recurrent_count: int,
    timeout_failure_count: int,
    rollback_signal_count: int,
    failure_count: int,
) -> int:
    penalty = 0
    penalty += min(45, recurrent_count * 12)
    penalty += min(25, timeout_failure_count * 4)
    penalty += min(15, rollback_signal_count * 5)
    penalty += min(10, failure_count)
    return max(0, 100 - penalty)


def _status(
    *,
    event_count: int,
    failure_count: int,
    recurrent_count: int,
    timeout_failure_count: int,
    baseline_created_at: str = "",
    historical_failure_count: int = 0,
    resolved_failure_count: int = 0,
) -> str:
    if resolved_failure_count and failure_count == 0:
        return "failures_resolved_by_followup_pass"
    if baseline_created_at and historical_failure_count and failure_count == 0:
        return "no_failures_since_baseline"
    if event_count == 0 or failure_count == 0:
        return "no_failures_observed"
    if recurrent_count:
        return "recurrent_failures_need_autopilot"
    if timeout_failure_count:
        return "transport_failures_observed"
    return "one_off_failures_observed"
