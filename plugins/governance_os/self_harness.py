"""Shadow Self-Harness candidate builder for Miho Governance OS."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

EVIDENCE_BUNDLE_SCHEMA = "miho-self-harness/evidence-bundle/v1"
SHADOW_CANDIDATE_SCHEMA = "miho-self-harness/shadow-candidate/v1"

_MIN_RECURRENCE_FLOOR = 2


def build_evidence_bundle(
    events: Iterable[dict[str, Any]],
    *,
    min_recurrence: int = _MIN_RECURRENCE_FLOOR,
) -> dict[str, Any]:
    """Group repeated governance failures without changing active runtime state."""

    recurrence_floor = max(_MIN_RECURRENCE_FLOOR, min_recurrence)
    groups: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)

    for event in events:
        outcome = _governance_outcome(event)
        playbook_key = _clean_text(outcome.get("playbook_key"))
        if not playbook_key:
            continue
        for failure in _string_list(outcome.get("failures")):
            groups[(playbook_key, failure)].append((event, outcome))

    patterns: list[dict[str, Any]] = []
    for (playbook_key, failure), records in sorted(groups.items()):
        if len(records) < recurrence_floor:
            continue
        patterns.append(
            {
                "id": _stable_id("pattern", playbook_key, failure, _evidence(records)),
                "playbook_key": playbook_key,
                "failure_signature": failure,
                "recurrence_count": len(records),
                "verifier_cause": failure,
                "agent_mechanism": _agent_mechanism(failure),
                "target_surface_hint": _target_surface(failure),
                "evidence": _evidence(records),
            }
        )

    return {
        "schema_version": EVIDENCE_BUNDLE_SCHEMA,
        "stage": "weakness_mining",
        "canonical_write": False,
        "active_registry_write": False,
        "pattern_count": len(patterns),
        "patterns": patterns,
    }


def build_shadow_candidates(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Build non-promoted harness proposals from mined repeated failures."""

    candidates: list[dict[str, Any]] = []
    for pattern in bundle.get("patterns", []):
        if not isinstance(pattern, dict):
            continue
        failure = _clean_text(pattern.get("failure_signature"))
        playbook_key = _clean_text(pattern.get("playbook_key"))
        if not failure or not playbook_key:
            continue

        target_surface = _target_surface(failure)
        candidates.append(
            {
                "schema_version": SHADOW_CANDIDATE_SCHEMA,
                "id": _stable_id("self-harness", playbook_key, failure, target_surface),
                "status": "shadow_candidate",
                "auto_promote_allowed": False,
                "target_surface": target_surface,
                "change_intent": _change_intent(target_surface, playbook_key, failure),
                "source_pattern": {
                    "id": pattern.get("id"),
                    "playbook_key": playbook_key,
                    "failure_signature": failure,
                    "recurrence_count": pattern.get("recurrence_count"),
                    "evidence": pattern.get("evidence", []),
                },
                "validation": {
                    "held_in_required": True,
                    "held_out_required": True,
                    "reviewer_required": True,
                    "required_tests": _required_tests(target_surface),
                },
                "rollback": "discard shadow candidate; active registry and runtime policy were not modified",
            }
        )

    return candidates


def _governance_outcome(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return {}
    outcome = metadata.get("governance_outcome")
    if not isinstance(outcome, dict):
        return {}
    return outcome


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [_clean_text(value)] if _clean_text(value) else []
    if not isinstance(value, list | tuple):
        return []

    cleaned: list[str] = []
    for item in value:
        text = _clean_text(item)
        if text:
            cleaned.append(text)
    return cleaned


def _clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _evidence(records: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[str]:
    lines: list[str] = []
    for event, outcome in records:
        event_id = event.get("id", "unknown")
        request_id = outcome.get("request_id", "unknown")
        review_status = outcome.get("review_status", "unknown")
        line = f"event={event_id} request_id={request_id} review_status={review_status}"
        feedback = _clean_text(outcome.get("user_feedback"))
        if feedback:
            line += f" feedback={feedback}"
        lines.append(line)
    return lines


def _target_surface(failure: str) -> str:
    normalized = failure.lower()
    if normalized.startswith("final_qa") or "answer" in normalized:
        return "final_qa_agent"
    if "attachment" in normalized or "delivery" in normalized or "media" in normalized:
        return "final_delivery_repair"
    if "pdf" in normalized or "footer" in normalized or "layout" in normalized:
        return "final_delivery_repair"
    if "reviewer" in normalized:
        return "domain_reviewer_contract"
    if "tool" in normalized or "forbidden" in normalized:
        return "tool_contract_guard"
    return "playbook_policy"


def _agent_mechanism(failure: str) -> str:
    target_surface = _target_surface(failure)
    if target_surface == "final_delivery_repair":
        return "physical delivery executor contract"
    if target_surface == "final_qa_agent":
        return "LLM final answer validator"
    if target_surface == "domain_reviewer_contract":
        return "domain-specific LLM reviewer routing"
    if target_surface == "tool_contract_guard":
        return "tool contract guard and reviewer handoff"
    return "playbook policy and outcome ledger"


def _change_intent(target_surface: str, playbook_key: str, failure: str) -> str:
    if target_surface == "final_delivery_repair":
        return (
            f"Propose a delivery-repair contract for {playbook_key} after repeated {failure}; "
            "only stage files or retry attachment paths, without semantic review."
        )
    if target_surface == "final_qa_agent":
        return (
            f"Propose a final QA prompt/check update for {playbook_key} after repeated {failure}; "
            "judge user-question fit and evidence consistency with an LLM."
        )
    if target_surface == "domain_reviewer_contract":
        return (
            f"Propose a domain reviewer routing update for {playbook_key} after repeated {failure}; "
            "use a domain-specific LLM reviewer before final delivery."
        )
    if target_surface == "tool_contract_guard":
        return (
            f"Propose a tool-contract guard update for {playbook_key} after repeated {failure}; "
            "preserve existing playbook behavior until validation passes."
        )
    return (
        f"Propose a playbook policy candidate for {playbook_key} after repeated {failure}; "
        "keep it shadow-only until held-in and held-out checks pass."
    )


def _required_tests(target_surface: str) -> list[str]:
    common = [
        "tests/plugins/test_governance_os_self_harness.py",
        "tests/plugins/test_governance_os_versioning.py",
    ]
    by_surface = {
        "final_delivery_repair": [
            "tests/tools/test_media_delivery_contract_tool.py",
            "tests/plugins/test_governance_os_review_retry.py",
        ],
        "final_qa_agent": [
            "tests/plugins/test_governance_os_final_qa.py",
            "tests/plugins/test_governance_os_delivery_gate.py",
        ],
        "domain_reviewer_contract": [
            "tests/plugins/test_governance_os_review_retry.py",
            "tests/plugins/test_governance_os_council.py",
        ],
        "tool_contract_guard": [
            "tests/plugins/test_governance_os_policy.py",
            "tests/plugins/test_governance_os_drills.py",
        ],
        "playbook_policy": [
            "tests/plugins/test_governance_os_promotion_activation.py",
        ],
    }
    return common + by_surface.get(target_surface, by_surface["playbook_policy"])


def _stable_id(prefix: str, *parts: object) -> str:
    payload = json.dumps(parts, ensure_ascii=True, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"
