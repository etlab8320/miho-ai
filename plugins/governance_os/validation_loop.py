"""Validation loop receipt scoring for Governance OS closure."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ADVERSARIAL_VALIDATOR_TASK = "miho_governance_adversarial_validator"

_REQUIRED_TESTS = ("focused_tests", "wider_gate", "runtime_readiness")
_REQUIRED_SMOKES = ("live_gateway_smoke", "attachment_artifact_smoke")


@dataclass(frozen=True)
class ValidationLoopReport:
    ready: bool
    score: int
    failures: tuple[str, ...] = field(default_factory=tuple)
    passed: tuple[str, ...] = field(default_factory=tuple)


def evaluate_validation_loop(
    *,
    test_receipts: tuple[dict[str, Any], ...],
    smoke_receipts: tuple[dict[str, Any], ...],
    adversarial_reviews: tuple[dict[str, Any], ...],
) -> ValidationLoopReport:
    failures: list[str] = []
    passed: list[str] = []
    checks: list[bool] = []

    for kind in _REQUIRED_TESTS:
        ok, failure = _required_passed_receipt(test_receipts, kind, label="test")
        checks.append(ok)
        if ok:
            passed.append(kind)
        else:
            failures.append(failure)

    for kind in _REQUIRED_SMOKES:
        ok, failure = _required_passed_smoke(smoke_receipts, kind)
        checks.append(ok)
        if ok:
            passed.append(kind)
        else:
            failures.append(failure)

    review_ok = any(_adversarial_review_passed(review) for review in adversarial_reviews)
    checks.append(review_ok)
    if review_ok:
        passed.append("independent_adversarial_review")
    else:
        failures.append("missing independent adversarial review")

    score = round((sum(1 for item in checks if item) / len(checks)) * 100)
    return ValidationLoopReport(
        ready=not failures,
        score=score,
        failures=tuple(failures),
        passed=tuple(passed),
    )


def _required_passed_receipt(
    receipts: tuple[dict[str, Any], ...],
    kind: str,
    *,
    label: str,
) -> tuple[bool, str]:
    receipt = _first_kind(receipts, kind)
    if receipt is None:
        return False, f"missing required {label}: {kind}"
    if not _receipt_passed(receipt):
        return False, f"failed required {label}: {kind}"
    if not str(receipt.get("command") or "").strip():
        return False, f"missing command evidence for {kind}"
    if not str(receipt.get("evidence") or "").strip():
        return False, f"missing receipt evidence for {kind}"
    return True, ""


def _required_passed_smoke(
    receipts: tuple[dict[str, Any], ...],
    kind: str,
) -> tuple[bool, str]:
    receipt = _first_kind(receipts, kind)
    if receipt is None:
        return False, f"missing required smoke: {kind}"
    if not _receipt_passed(receipt):
        return False, f"failed required smoke: {kind}"
    if not str(receipt.get("evidence") or "").strip():
        return False, f"missing smoke evidence for {kind}"
    if kind == "live_gateway_smoke":
        mode = str(receipt.get("mode") or "").strip()
        if mode not in {"live", "live_safe"}:
            return False, "live gateway smoke must declare live or live_safe mode"
    if kind == "attachment_artifact_smoke" and not _artifact_smoke_passed(receipt):
        return False, "attachment artifact smoke did not prove deliverable MEDIA artifact"
    return True, ""


def _artifact_smoke_passed(receipt: dict[str, Any]) -> bool:
    raw_path = str(receipt.get("artifact_path") or "").strip().strip("`")
    media_tag = str(receipt.get("media_tag") or "").strip()
    if not raw_path or not media_tag.startswith("MEDIA:"):
        return False
    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return False
    return path.is_file() and raw_path in media_tag


def _adversarial_review_passed(review: dict[str, Any]) -> bool:
    if str(review.get("status") or "").strip() not in {"pass", "passed"}:
        return False
    if review.get("independent") is not True:
        return False
    if str(review.get("task") or "").strip() != ADVERSARIAL_VALIDATOR_TASK:
        return False
    if str(review.get("reviewer") or "").strip().casefold() in {"", "builder", "self"}:
        return False
    if _score(review.get("score")) < 95:
        return False
    findings = review.get("findings")
    return isinstance(findings, list) and len(findings) == 0


def _first_kind(receipts: tuple[dict[str, Any], ...], kind: str) -> dict[str, Any] | None:
    for receipt in receipts:
        if str(receipt.get("kind") or "") == kind:
            return receipt
    return None


def _receipt_passed(receipt: dict[str, Any]) -> bool:
    status = str(receipt.get("status") or "").strip()
    exit_code = receipt.get("exit_code")
    return status in {"pass", "passed", "success"} and exit_code in {None, 0}


def _score(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
