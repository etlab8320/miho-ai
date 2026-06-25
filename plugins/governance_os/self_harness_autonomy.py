"""Autonomous activation loop for Miho Self-Harness candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from .promotion import (
    PromotionActivation,
    PromotionCandidate,
    PromotionTestReceipt,
    activate_promotion_candidate,
)

AutonomousAction = Literal["hold", "activate"]

_PASS_STATUSES = {"pass", "passed", "ok", "success", "succeeded", "green"}
_FAIL_STATUSES = {"fail", "failed", "error", "blocked", "red"}
_GATE_BY_SURFACE = {
    "final_delivery_repair": "final_delivery_repair",
    "final_qa_agent": "final_qa_agent",
    "domain_reviewer_contract": "domain_reviewer",
    "tool_contract_guard": "tool_contract_guard",
    "playbook_policy": "self_harness_policy_review",
}


def decide_autonomous_activation(
    candidate: dict[str, Any],
    *,
    test_receipts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Decide whether a shadow candidate can autonomously activate."""

    errors = _candidate_contract_errors(candidate)
    receipts, invalid_receipts = _normalize_receipts(test_receipts)
    required_tests = _required_tests(candidate)
    passed_names = tuple(receipt.name for receipt in receipts if receipt.passed)
    failed_tests = [receipt.name for receipt in receipts if not receipt.passed]
    missing_tests = _missing_required_tests(required_tests, passed_names)

    can_activate = not errors and not invalid_receipts and not failed_tests and not missing_tests
    action: AutonomousAction = "activate" if can_activate else "hold"
    return {
        "schema_version": "miho-self-harness/autonomous-decision/v1",
        "action": action,
        "candidate_id": str(candidate.get("id") or ""),
        "target_surface": str(candidate.get("target_surface") or ""),
        "active_registry_write": action == "activate",
        "user_approval_required": False,
        "rollback_required": True,
        "required_tests": list(required_tests),
        "missing_tests": missing_tests,
        "failed_tests": failed_tests,
        "invalid_receipts": invalid_receipts,
        "contract_errors": errors,
        "reason": "validated_autonomous_activation" if can_activate else "validation_incomplete",
    }


def activate_autonomous_candidate(
    candidate: dict[str, Any],
    *,
    test_receipts: Sequence[Mapping[str, Any]],
    registry: Any = None,
    created_at: str = "",
    base_dir: Any = None,
) -> PromotionActivation:
    """Activate a validated candidate without requiring user approval."""

    decision = decide_autonomous_activation(candidate, test_receipts=test_receipts)
    if decision["action"] != "activate":
        details = ", ".join(
            [
                *(f"missing:{item}" for item in decision["missing_tests"]),
                *(f"failed:{item}" for item in decision["failed_tests"]),
                *(f"contract:{item}" for item in decision["contract_errors"]),
            ]
        )
        raise ValueError(details or "self-harness candidate is not ready")

    promotion = _promotion_candidate(candidate)
    receipts, _invalid = _normalize_receipts(test_receipts)
    surface = str(candidate.get("target_surface") or "")
    return activate_promotion_candidate(
        promotion,
        action="add_review_gate",
        value=_gate_for_surface(surface),
        registry=registry,
        test_receipts=tuple(receipt.to_metadata() for receipt in receipts),
        reason=f"self-harness autonomous activation: {surface}",
        created_at=created_at,
        base_dir=base_dir,
    )


def rollback_on_regression(
    activation: PromotionActivation,
    *,
    regression_receipts: Sequence[Mapping[str, Any]],
    base_dir: Any = None,
) -> Any | None:
    """Rollback an autonomous activation when post-activation receipts fail."""

    receipts, invalid_count = _normalize_receipts(regression_receipts)
    if invalid_count:
        from .versioning import rollback_registry_snapshot

        return rollback_registry_snapshot(
            activation.rollback_snapshot_id,
            reason="self-harness rollback: invalid regression receipt",
            base_dir=base_dir,
        )
    if all(receipt.passed for receipt in receipts):
        return None

    from .versioning import rollback_registry_snapshot

    return rollback_registry_snapshot(
        activation.rollback_snapshot_id,
        reason="self-harness rollback: post-activation regression failed",
        base_dir=base_dir,
    )


def _candidate_contract_errors(candidate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if candidate.get("schema_version") != "miho-self-harness/shadow-candidate/v1":
        errors.append("schema_version must be shadow-candidate/v1")
    if candidate.get("status") != "shadow_candidate":
        errors.append("status must be shadow_candidate")
    if candidate.get("auto_promote_allowed") is not False:
        errors.append("candidate must start with auto_promote_allowed=false")
    if not str(candidate.get("target_surface") or "").strip():
        errors.append("target_surface is required")
    if not str(candidate.get("rollback") or "").strip():
        errors.append("rollback is required")

    validation = candidate.get("validation")
    if not isinstance(validation, dict):
        errors.append("validation is required")
        return errors
    if validation.get("held_in_required") is not True:
        errors.append("held_in_required must be true")
    if validation.get("held_out_required") is not True:
        errors.append("held_out_required must be true")
    if validation.get("reviewer_required") is not True:
        errors.append("reviewer_required must be true")
    if not _required_tests(candidate):
        errors.append("required_tests is required")
    return errors


def _promotion_candidate(candidate: dict[str, Any]) -> PromotionCandidate:
    source = candidate.get("source_pattern")
    if not isinstance(source, dict):
        raise ValueError("source_pattern is required")
    playbook_key = str(source.get("playbook_key") or "").strip()
    failure = str(source.get("failure_signature") or "").strip()
    recurrence_count = int(source.get("recurrence_count") or 0)
    evidence = tuple(str(item) for item in source.get("evidence") or ())
    return PromotionCandidate(
        playbook_key=playbook_key,
        source_failure=failure,
        recurrence_count=recurrence_count,
        proposed_policy=str(candidate.get("change_intent") or "self-harness autonomous update"),
        evidence=evidence,
        tests_required=_required_tests(candidate),
        rollback=str(candidate.get("rollback") or "rollback active governance registry snapshot"),
    )


def _required_tests(candidate: dict[str, Any]) -> tuple[str, ...]:
    validation = candidate.get("validation")
    if not isinstance(validation, dict):
        return ()
    raw = validation.get("required_tests")
    if not isinstance(raw, list | tuple):
        return ()
    return tuple(str(item).strip() for item in raw if str(item).strip())


def _normalize_receipts(
    value: Sequence[Mapping[str, Any]],
) -> tuple[tuple[PromotionTestReceipt, ...], int]:
    receipts: list[PromotionTestReceipt] = []
    invalid_count = 0
    for item in value:
        receipt = _receipt_from_mapping(item)
        if receipt is None:
            invalid_count += 1
            continue
        receipts.append(receipt)
    return tuple(receipts), invalid_count


def _receipt_from_mapping(item: Mapping[str, Any]) -> PromotionTestReceipt | None:
    name = str(item.get("name") or "").strip()
    command = str(item.get("command") or "").strip()
    evidence = str(item.get("evidence") or "").strip()
    if not name or not (command or evidence):
        return None
    status = str(item.get("status") or "").strip()
    exit_code = _optional_int(item.get("exit_code"))
    passed = _receipt_passed(status, item.get("success"), exit_code)
    return PromotionTestReceipt(
        name=name,
        passed=passed,
        status=status,
        exit_code=exit_code,
        command=command,
        evidence=evidence,
    )


def _receipt_passed(status: str, success: Any, exit_code: int | None) -> bool:
    normalized = status.casefold()
    if normalized in _FAIL_STATUSES:
        return False
    if success is False:
        return False
    if normalized in _PASS_STATUSES:
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


def _missing_required_tests(required: tuple[str, ...], passed: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for required_test in required:
        if not any(_receipt_name_matches(required_test, item) for item in passed):
            missing.append(required_test)
    return missing


def _receipt_name_matches(required_test: str, receipt_name: str) -> bool:
    required = required_test.strip()
    name = receipt_name.strip()
    return name == required or name.startswith(f"{required}::")


def _gate_for_surface(surface: str) -> str:
    return _GATE_BY_SURFACE.get(surface, _GATE_BY_SURFACE["playbook_policy"])
