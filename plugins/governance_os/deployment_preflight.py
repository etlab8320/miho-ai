"""Deployment preflight gates for Governance OS runtime operations."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .operations import GovernanceReadinessReport, run_readiness_check


@dataclass(frozen=True)
class DeploymentReceipt:
    name: str
    passed: bool
    status: str = ""
    exit_code: int | None = None
    command: str = ""
    evidence: str = ""
    source: str = ""
    verified_at: int | None = None
    command_hash: str = ""

    def to_metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "status": self.status,
            "exit_code": self.exit_code,
            "command": self.command,
            "evidence": self.evidence,
            "source": self.source,
            "verified_at": self.verified_at,
            "command_hash": self.command_hash,
        }


@dataclass(frozen=True)
class DeploymentPreflightReport:
    target: str
    ready: bool
    readiness_ready: bool
    readiness_quality_score: int
    tests_passed: bool
    smoke_passed: bool
    config_passed: bool
    rollback_plan_passed: bool
    required_test_receipts: tuple[str, ...]
    required_smoke_receipts: tuple[str, ...]
    required_config_checks: tuple[str, ...]
    test_receipts: tuple[DeploymentReceipt, ...] = field(default_factory=tuple)
    smoke_receipts: tuple[DeploymentReceipt, ...] = field(default_factory=tuple)
    config_checks: tuple[DeploymentReceipt, ...] = field(default_factory=tuple)
    rollback_plan: str = ""
    failures: tuple[str, ...] = field(default_factory=tuple)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "ready": self.ready,
            "readiness_ready": self.readiness_ready,
            "readiness_quality_score": self.readiness_quality_score,
            "tests_passed": self.tests_passed,
            "smoke_passed": self.smoke_passed,
            "config_passed": self.config_passed,
            "rollback_plan_passed": self.rollback_plan_passed,
            "required_test_receipts": list(self.required_test_receipts),
            "required_smoke_receipts": list(self.required_smoke_receipts),
            "required_config_checks": list(self.required_config_checks),
            "test_receipts": [item.to_metadata() for item in self.test_receipts],
            "smoke_receipts": [item.to_metadata() for item in self.smoke_receipts],
            "config_checks": [item.to_metadata() for item in self.config_checks],
            "rollback_plan": self.rollback_plan,
            "failures": list(self.failures),
        }


@dataclass(frozen=True)
class _ReceiptGate:
    passed: bool
    receipts: tuple[DeploymentReceipt, ...]
    failures: tuple[str, ...]


_PASS_STATUSES = {"pass", "passed", "ok", "success", "succeeded", "green"}
_FAIL_STATUSES = {"fail", "failed", "error", "blocked", "red"}
_LOCAL_RECEIPT_SOURCE = "governance_os_local"
_MAX_RECEIPT_AGE_SECONDS = 24 * 60 * 60
_MAX_RECEIPT_CLOCK_SKEW_SECONDS = 5 * 60
_DEFAULT_PREFLIGHT_REQUIREMENTS = {
    "gateway_restart": {
        "tests": ("related_governance_suite", "static_checks"),
        "smoke": ("governance_status", "discord_delivery"),
        "config": ("gateway_service_definition",),
    }
}


def build_verification_receipt(
    *,
    name: str,
    command: str,
    evidence: str,
    status: str = "passed",
    exit_code: int | None = 0,
    verified_at: int | None = None,
) -> dict[str, Any]:
    normalized_command = str(command or "").strip()
    return {
        "name": str(name or "").strip(),
        "status": str(status or "").strip(),
        "exit_code": exit_code,
        "command": normalized_command,
        "evidence": str(evidence or "").strip(),
        "source": _LOCAL_RECEIPT_SOURCE,
        "verified_at": int(time.time()) if verified_at is None else int(verified_at),
        "command_hash": _command_hash(normalized_command),
    }


def run_deployment_preflight(
    *,
    target: str = "gateway_restart",
    test_receipts: Any = None,
    smoke_receipts: Any = None,
    config_checks: Any = None,
    rollback_plan: str = "",
    readiness_report: GovernanceReadinessReport | None = None,
) -> DeploymentPreflightReport:
    normalized_target = _target_key(target)
    requirements = _preflight_requirements(normalized_target)
    readiness = readiness_report or run_readiness_check()
    failures: list[str] = []

    if not readiness.ready or readiness.quality_score < 100:
        failures.append("readiness check must be ready with quality score 100")

    test_gate = _evaluate_receipts(
        "test",
        test_receipts,
        required=requirements["tests"],
    )
    smoke_gate = _evaluate_receipts(
        "smoke",
        smoke_receipts,
        required=requirements["smoke"],
    )
    config_gate = _evaluate_receipts(
        "config",
        config_checks,
        required=requirements["config"],
    )
    failures.extend(test_gate.failures)
    failures.extend(smoke_gate.failures)
    failures.extend(config_gate.failures)

    normalized_rollback = _compact_text(rollback_plan)
    rollback_passed = _rollback_plan_passed(normalized_rollback)
    if not rollback_passed:
        failures.append("rollback plan is required")

    ready = (
        not failures
        and readiness.ready
        and readiness.quality_score == 100
        and test_gate.passed
        and smoke_gate.passed
        and config_gate.passed
        and rollback_passed
    )
    return DeploymentPreflightReport(
        target=normalized_target,
        ready=ready,
        readiness_ready=readiness.ready,
        readiness_quality_score=readiness.quality_score,
        tests_passed=test_gate.passed,
        smoke_passed=smoke_gate.passed,
        config_passed=config_gate.passed,
        rollback_plan_passed=rollback_passed,
        required_test_receipts=requirements["tests"],
        required_smoke_receipts=requirements["smoke"],
        required_config_checks=requirements["config"],
        test_receipts=test_gate.receipts,
        smoke_receipts=smoke_gate.receipts,
        config_checks=config_gate.receipts,
        rollback_plan=normalized_rollback,
        failures=tuple(failures),
    )


def _evaluate_receipts(
    label: str,
    value: Any,
    *,
    required: tuple[str, ...],
) -> _ReceiptGate:
    receipts, invalid_count = _normalize_receipts(value)
    by_name = {receipt.name: receipt for receipt in receipts}
    passed_names = {receipt.name for receipt in receipts if receipt.passed}
    failures: list[str] = []
    failure_label = _receipt_failure_label(label)
    if invalid_count:
        failures.append(f"invalid {failure_label}: {invalid_count}")

    failed = tuple(name for name in required if name in by_name and name not in passed_names)
    if failed:
        failures.append(f"failed {failure_label}: {', '.join(failed)}")

    missing = tuple(name for name in required if name not in passed_names)
    if missing:
        failures.append(f"missing {failure_label}: {', '.join(missing)}")

    return _ReceiptGate(
        passed=not failures,
        receipts=receipts,
        failures=tuple(failures),
    )


def _receipt_failure_label(label: str) -> str:
    if label == "config":
        return "config checks"
    return f"{label} receipts"


def _normalize_receipts(value: Any) -> tuple[tuple[DeploymentReceipt, ...], int]:
    if value is None:
        return (), 0
    items = value if isinstance(value, (list, tuple)) else (value,)
    receipts: list[DeploymentReceipt] = []
    invalid_count = 0
    for item in items:
        if not isinstance(item, Mapping):
            invalid_count += 1
            continue
        receipt = _receipt_from_mapping(item)
        if receipt is None:
            invalid_count += 1
            continue
        receipts.append(receipt)
    return tuple(receipts), invalid_count


def _receipt_from_mapping(item: Mapping[str, Any]) -> DeploymentReceipt | None:
    name = str(item.get("name") or "").strip()
    command = str(item.get("command") or "").strip()
    evidence = str(item.get("evidence") or "").strip()
    source = str(item.get("source") or "").strip()
    verified_at = _optional_int(item.get("verified_at"))
    command_hash = str(item.get("command_hash") or "").strip()
    if not name or not command or not evidence:
        return None
    if not _receipt_is_trusted(
        command=command,
        source=source,
        verified_at=verified_at,
        command_hash=command_hash,
    ):
        return None
    status = str(item.get("status") or "").strip()
    exit_code = _optional_int(item.get("exit_code"))
    passed = _receipt_passed(status, item.get("success"), exit_code)
    return DeploymentReceipt(
        name=name,
        passed=passed,
        status=status,
        exit_code=exit_code,
        command=command,
        evidence=evidence,
        source=source,
        verified_at=verified_at,
        command_hash=command_hash,
    )


def _receipt_is_trusted(
    *,
    command: str,
    source: str,
    verified_at: int | None,
    command_hash: str,
) -> bool:
    if source != _LOCAL_RECEIPT_SOURCE:
        return False
    if verified_at is None or verified_at <= 0:
        return False
    if command_hash != _command_hash(command):
        return False
    now = int(time.time())
    if verified_at > now + _MAX_RECEIPT_CLOCK_SKEW_SECONDS:
        return False
    return now - verified_at <= _MAX_RECEIPT_AGE_SECONDS


def _command_hash(command: str) -> str:
    return hashlib.sha256(str(command or "").strip().encode("utf-8")).hexdigest()


def _receipt_passed(status: str, success: Any, exit_code: int | None) -> bool:
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


def _rollback_plan_passed(plan: str) -> bool:
    if not plan or plan.casefold() in {"none", "no", "n/a", "없음"}:
        return False
    markers = ("rollback", "revert", "restore", "previous", "snapshot", "되돌", "복구", "이전")
    lowered = plan.casefold()
    return len(plan) >= 20 and any(marker in lowered for marker in markers)


def _preflight_requirements(target: str) -> dict[str, tuple[str, ...]]:
    return _DEFAULT_PREFLIGHT_REQUIREMENTS.get(
        target,
        _DEFAULT_PREFLIGHT_REQUIREMENTS["gateway_restart"],
    )


def _target_key(value: str) -> str:
    target = str(value or "").strip()
    return target or "gateway_restart"


def _compact_text(text: str) -> str:
    return " ".join(str(text or "").split())
