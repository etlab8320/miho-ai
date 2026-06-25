"""Promotion candidate bridge for Governance OS rules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal


PromotionAction = Literal["add_forbidden_tool", "add_required_tool", "add_review_gate"]

_REQUIRED_PROMOTION_SAFETY_TESTS = (
    "tests/plugins/test_governance_os_promotion_activation.py",
    "tests/plugins/test_governance_os_versioning.py",
)
_DEFAULT_PROMOTION_TESTS = (
    "tests/plugins/test_governance_os_policy.py",
    "tests/plugins/test_governance_os_review_retry.py",
)
_PROMOTION_TESTS_BY_PLAYBOOK: dict[str, tuple[str, ...]] = {
    "academy_hakjong_report": ("tests/plugins/test_academy_result_reviewer.py",),
    "academy_practical_reco": (
        "tests/plugins/test_academy_result_reviewer.py",
        "tests/plugins/test_academy_practical_reco.py",
    ),
    "discord_attachment_delivery": (
        "tests/e2e/test_discord_governance_delivery.py",
        "tests/tools/test_media_delivery_contract_tool.py",
    ),
    "research_brief": ("tests/plugins/test_governance_os_council.py",),
    "memory_policy_update": ("tests/plugins/test_governance_os_simulator.py",),
}
_PROMOTION_TESTS_BY_FAILURE: dict[str, tuple[str, ...]] = {
    "forbidden_tool": (
        "tests/plugins/test_governance_os_policy.py",
        "tests/plugins/test_governance_os_drills.py",
    ),
    "reviewer_missing": (
        "tests/plugins/test_governance_os_review_retry.py",
        "tests/plugins/test_governance_os_council.py",
    ),
}
_PASS_STATUSES = {"pass", "passed", "ok", "success", "succeeded", "green"}
_FAIL_STATUSES = {"fail", "failed", "error", "blocked", "red"}


@dataclass(frozen=True)
class PromotionCandidate:
    playbook_key: str
    source_failure: str
    recurrence_count: int
    proposed_policy: str
    evidence: tuple[str, ...] = field(default_factory=tuple)
    tests_required: tuple[str, ...] = field(default_factory=tuple)
    rollback: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return {
            "playbook_key": self.playbook_key,
            "source_failure": self.source_failure,
            "recurrence_count": int(self.recurrence_count),
            "proposed_policy": self.proposed_policy,
            "evidence": list(self.evidence),
            "tests_required": list(self.tests_required),
            "rollback": self.rollback,
        }


@dataclass(frozen=True)
class PromotionActivation:
    playbook_key: str
    action: PromotionAction
    value: str
    snapshot_id: str
    rollback_snapshot_id: str
    fingerprint: str
    event_id: int

    def to_metadata(self) -> dict[str, Any]:
        return {
            "playbook_key": self.playbook_key,
            "action": self.action,
            "value": self.value,
            "snapshot_id": self.snapshot_id,
            "rollback_snapshot_id": self.rollback_snapshot_id,
            "fingerprint": self.fingerprint,
            "event_id": self.event_id,
        }


@dataclass(frozen=True)
class PromotionTestReceipt:
    name: str
    passed: bool
    status: str = ""
    exit_code: int | None = None
    command: str = ""
    evidence: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "status": self.status,
            "exit_code": self.exit_code,
            "command": self.command,
            "evidence": self.evidence,
        }


def validate_candidate(candidate: PromotionCandidate) -> list[str]:
    errors: list[str] = []
    if not candidate.playbook_key.strip():
        errors.append("playbook_key is required")
    if not candidate.source_failure.strip():
        errors.append("source_failure is required")
    if candidate.recurrence_count < 2:
        errors.append("recurrence_count must be at least 2")
    if not candidate.proposed_policy.strip():
        errors.append("proposed_policy is required")
    if not candidate.evidence:
        errors.append("evidence is required")
    if not candidate.tests_required:
        errors.append("tests_required is required")
    if not candidate.rollback.strip():
        errors.append("rollback is required")
    return errors


def activate_promotion_candidate(
    candidate: PromotionCandidate,
    *,
    action: PromotionAction,
    value: str,
    reason: str,
    tests_passed: tuple[str, ...] = (),
    test_receipts: Any = None,
    registry: Any = None,
    created_at: str = "",
    base_dir: Path | None = None,
) -> PromotionActivation:
    errors = validate_candidate(candidate)
    if errors:
        raise ValueError("; ".join(errors))
    receipts, invalid_count = _normalize_test_receipts(test_receipts)
    if invalid_count:
        raise ValueError(f"invalid test receipts: {invalid_count}")
    if not receipts:
        raise ValueError("test_receipts is required")
    failed = tuple(receipt.name for receipt in receipts if not receipt.passed)
    if failed:
        raise ValueError(f"required tests did not pass: {', '.join(failed)}")
    passed = tuple(receipt.name for receipt in receipts if receipt.passed)
    legacy_passed = tuple(str(item).strip() for item in tests_passed if str(item).strip())
    missing = _missing_required_tests(candidate.tests_required, passed)
    if missing:
        raise ValueError(f"required tests did not pass: {', '.join(missing)}")
    clean_value = value.strip()
    if not clean_value:
        raise ValueError("promotion value is required")

    from .versioning import activate_registry_snapshot, load_runtime_registry, snapshot_registry

    base_registry = registry if registry is not None else load_runtime_registry(base_dir=base_dir)
    rollback_snapshot = snapshot_registry(
        base_registry,
        reason=f"pre-promotion rollback: {candidate.playbook_key}",
        created_at=created_at,
        base_dir=base_dir,
    )
    promoted_registry = _apply_registry_change(
        base_registry,
        playbook_key=candidate.playbook_key,
        action=action,
        value=clean_value,
    )
    promoted_snapshot = snapshot_registry(
        promoted_registry,
        reason=reason,
        created_at=created_at,
        base_dir=base_dir,
    )
    activate_registry_snapshot(
        promoted_snapshot.snapshot_id,
        reason=reason,
        base_dir=base_dir,
        record_event=False,
    )

    from agent import evolution

    metadata = {
        "candidate": candidate.to_metadata(),
        "action": action,
        "value": clean_value,
        "tests_passed": list(passed),
        "legacy_tests_passed": list(legacy_passed),
        "test_receipts": [item.to_metadata() for item in receipts],
        "snapshot_id": promoted_snapshot.snapshot_id,
        "rollback_snapshot_id": rollback_snapshot.snapshot_id,
        "fingerprint": promoted_snapshot.fingerprint,
    }
    event = evolution.record_event(
        kind="promotion",
        title=f"Governance promotion {candidate.playbook_key}: {action} {clean_value}",
        summary=reason,
        snapshot_id=promoted_snapshot.snapshot_id,
        status="promoted",
        metadata={"governance_promotion_activation": metadata},
    )
    activation = PromotionActivation(
        playbook_key=candidate.playbook_key,
        action=action,
        value=clean_value,
        snapshot_id=promoted_snapshot.snapshot_id,
        rollback_snapshot_id=rollback_snapshot.snapshot_id,
        fingerprint=promoted_snapshot.fingerprint,
        event_id=int(event["id"]),
    )
    return activation


def record_promotion_candidate(candidate: PromotionCandidate) -> dict[str, Any]:
    errors = validate_candidate(candidate)
    if errors:
        raise ValueError("; ".join(errors))

    from agent import evolution

    metadata = candidate.to_metadata()
    return evolution.record_event(
        kind="failure_pattern",
        title=f"Governance candidate {candidate.playbook_key}: {candidate.source_failure}",
        summary=candidate.proposed_policy,
        evidence="\n".join(candidate.evidence),
        status="candidate",
        metadata={"governance_promotion_candidate": metadata},
    )


def find_promotion_candidates(
    *,
    limit: int = 100,
    min_recurrence: int = 2,
) -> list[PromotionCandidate]:
    from agent import evolution

    events = evolution.list_events(limit=max(1, int(limit)))
    return detect_promotion_candidates(events, min_recurrence=min_recurrence)


def detect_promotion_candidates(
    events: Iterable[dict[str, Any]],
    *,
    min_recurrence: int = 2,
) -> list[PromotionCandidate]:
    threshold = max(2, int(min_recurrence))
    groups: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for event in events:
        outcome = _governance_outcome(event)
        if not outcome:
            continue
        playbook_key = str(outcome.get("playbook_key") or "").strip()
        if not playbook_key:
            continue
        for failure in _tuple_str(outcome.get("failures")):
            groups.setdefault((playbook_key, failure), []).append((event, outcome))

    candidates: list[PromotionCandidate] = []
    for (playbook_key, failure), records in sorted(groups.items()):
        if len(records) < threshold:
            continue
        candidates.append(
            PromotionCandidate(
                playbook_key=playbook_key,
                source_failure=failure,
                recurrence_count=len(records),
                proposed_policy=_proposed_policy(playbook_key, failure),
                evidence=_candidate_evidence(records),
                tests_required=_tests_required(playbook_key, failure),
                rollback="rollback active governance registry snapshot",
            )
        )
    return sorted(
        candidates,
        key=lambda item: (-item.recurrence_count, item.playbook_key, item.source_failure),
    )


def _missing_required_tests(required: tuple[str, ...], passed: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for required_test in required:
        if not any(_receipt_name_matches_required(required_test, item) for item in passed):
            missing.append(required_test)
    return missing


def _receipt_name_matches_required(required_test: str, receipt_name: str) -> bool:
    required = required_test.strip()
    name = receipt_name.strip()
    return name == required or name.startswith(f"{required}::")


def _normalize_test_receipts(value: Any) -> tuple[tuple[PromotionTestReceipt, ...], int]:
    if value is None:
        return (), 0
    if not isinstance(value, (list, tuple)):
        return (), 1
    items = value
    receipts: list[PromotionTestReceipt] = []
    invalid_count = 0
    for item in items:
        if not isinstance(item, Mapping):
            invalid_count += 1
            continue
        receipt = _test_receipt_from_mapping(item)
        if receipt is None:
            invalid_count += 1
            continue
        receipts.append(receipt)
    return tuple(receipts), invalid_count


def _test_receipt_from_mapping(item: Mapping[str, Any]) -> PromotionTestReceipt | None:
    name = str(item.get("name") or "").strip()
    command = str(item.get("command") or "").strip()
    evidence = str(item.get("evidence") or "").strip()
    if not name or not (command or evidence):
        return None
    status = str(item.get("status") or "").strip()
    exit_code = _optional_int(item.get("exit_code"))
    passed = _test_receipt_passed(status, item.get("success"), exit_code)
    return PromotionTestReceipt(
        name=name,
        passed=passed,
        status=status,
        exit_code=exit_code,
        command=command,
        evidence=evidence,
    )


def _test_receipt_passed(status: str, success: Any, exit_code: int | None) -> bool:
    normalized_status = status.casefold()
    if normalized_status in _FAIL_STATUSES:
        return False
    if success is False:
        return False
    if normalized_status in _PASS_STATUSES:
        return True
    if success is True:
        return True
    return exit_code == 0


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _apply_registry_change(
    registry: Any,
    *,
    playbook_key: str,
    action: PromotionAction,
    value: str,
) -> Any:
    from .registry import registry_from_mapping

    payload = registry.to_payload()
    playbooks = payload.get("playbooks") or {}
    if playbook_key not in playbooks:
        raise ValueError(f"unknown playbook {playbook_key!r}")
    playbook = playbooks[playbook_key]
    field_name = _field_for_action(action)
    items = list(playbook.get(field_name) or [])
    if value not in items:
        items.append(value)
    playbook[field_name] = items
    _reject_conflicting_tool_contract(playbook, action, value)
    return registry_from_mapping(payload)


def _field_for_action(action: PromotionAction) -> str:
    if action == "add_forbidden_tool":
        return "forbidden_tools"
    if action == "add_required_tool":
        return "required_tools"
    if action == "add_review_gate":
        return "review_gates"
    raise ValueError(f"unsupported promotion action {action!r}")


def _reject_conflicting_tool_contract(
    playbook: dict[str, Any],
    action: PromotionAction,
    value: str,
) -> None:
    if action == "add_forbidden_tool" and value in set(playbook.get("required_tools") or []):
        raise ValueError(f"tool {value!r} cannot be both required and forbidden")
    if action == "add_required_tool" and value in set(playbook.get("forbidden_tools") or []):
        raise ValueError(f"tool {value!r} cannot be both required and forbidden")


def _governance_outcome(event: dict[str, Any]) -> dict[str, Any] | None:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return None
    outcome = metadata.get("governance_outcome")
    return outcome if isinstance(outcome, dict) else None


def _candidate_evidence(
    records: list[tuple[dict[str, Any], dict[str, Any]]],
) -> tuple[str, ...]:
    evidence: list[str] = []
    for event, outcome in sorted(records, key=lambda item: int(item[0].get("id") or 0)):
        event_id = int(event.get("id") or 0)
        request_id = str(outcome.get("request_id") or "").strip()
        review_status = str(outcome.get("review_status") or "unknown").strip()
        evidence.append(
            f"event={event_id} request_id={request_id} review_status={review_status}"
        )
    return tuple(evidence)


def _proposed_policy(playbook_key: str, failure: str) -> str:
    if failure == "reviewer_missing":
        return f"enforce review gate retry for {playbook_key} before delivery"
    if failure == "forbidden_tool":
        return f"tighten forbidden tool guard for repeated {playbook_key} bypasses"
    if failure.startswith("reviewer_"):
        return f"strengthen reviewer contract for {playbook_key}: {failure}"
    return f"promote guarded handling for repeated {playbook_key} failure: {failure}"


def _tests_required(playbook_key: str, failure: str) -> tuple[str, ...]:
    return _dedupe_tests(
        _PROMOTION_TESTS_BY_PLAYBOOK.get(playbook_key, _DEFAULT_PROMOTION_TESTS),
        _PROMOTION_TESTS_BY_FAILURE.get(failure, ()),
        _REQUIRED_PROMOTION_SAFETY_TESTS,
    )


def _dedupe_tests(*groups: tuple[str, ...]) -> tuple[str, ...]:
    tests: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for test_path in group:
            if test_path in seen:
                continue
            seen.add(test_path)
            tests.append(test_path)
    return tuple(tests)


def _tuple_str(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    return (text,) if text else ()
