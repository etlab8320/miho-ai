"""Tool wrapper for Miho Governance OS operations."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, cast

from tools.registry import registry, tool_error, tool_result


logger = logging.getLogger(__name__)
_UNKNOWN_ACTION_ERROR = (
    "알 수 없는 거버넌스 OS 작업입니다. status, drills, simulate, preflight, promotions, promote, "
    "outcomes, packs, snapshot, activate, rollback 중 하나를 사용해 주세요."
)
_INTERNAL_ERROR = "거버넌스 OS 작업 중 문제가 발생했습니다. 검증 로그를 확인하고 다시 시도해 주세요."
_PROMOTION_ACTIONS = frozenset({"add_forbidden_tool", "add_required_tool", "add_review_gate"})


GOVERNANCE_OS_SCHEMA = {
    "name": "governance_os",
    "description": (
        "Operate Miho Governance OS: inspect runtime readiness, outcomes, drills, "
        "scenario simulations, domain packs, promotion candidates, and versioned "
        "registry snapshots, activation, and rollback."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "status",
                    "drills",
                    "simulate",
                    "preflight",
                    "promotions",
                    "promote",
                    "outcomes",
                    "packs",
                    "snapshot",
                    "activate",
                    "rollback",
                ],
                "description": "Governance OS action to perform.",
            },
            "target": {
                "type": "string",
                "description": "Deployment target for action=preflight, e.g. gateway_restart.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum ledger events to inspect.",
            },
            "min_recurrence": {
                "type": "integer",
                "description": "Minimum repeated failures required for promotion candidacy.",
            },
            "playbook_key": {
                "type": "string",
                "description": "Optional playbook key filter for outcome ledger queries.",
            },
            "promotion_action": {
                "type": "string",
                "enum": ["add_forbidden_tool", "add_required_tool", "add_review_gate"],
                "description": "Registry mutation to apply when action=promote.",
            },
            "value": {
                "type": "string",
                "description": "Tool or review gate value to promote into the registry.",
            },
            "source_failure": {
                "type": "string",
                "description": "Repeated failure that caused the promotion candidate.",
            },
            "recurrence_count": {
                "type": "integer",
                "description": "Observed recurrence count for the failure.",
            },
            "proposed_policy": {
                "type": "string",
                "description": "Human-readable policy proposed for promotion.",
            },
            "evidence": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Evidence lines supporting the promotion.",
            },
            "tests_required": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tests required before the promotion can activate.",
            },
            "tests_passed": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Legacy test-name claims. Promote requires structured test_receipts.",
            },
            "test_receipts": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Structured test receipts for action=preflight or action=promote.",
            },
            "smoke_receipts": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Structured runtime smoke receipts for action=preflight.",
            },
            "config_checks": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Structured config-check receipts for action=preflight.",
            },
            "rollback_plan": {
                "type": "string",
                "description": "Concrete rollback plan required for action=preflight.",
            },
            "snapshot_id": {
                "type": "string",
                "description": "Registry snapshot id for activate or rollback.",
            },
            "reason": {
                "type": "string",
                "description": "Audit reason for snapshot, activation, or rollback.",
            },
        },
        "required": ["action"],
    },
}


def governance_os_tool(args: dict[str, Any]) -> str:
    action = str(args.get("action") or "").strip()
    try:
        if action == "status":
            return _status()
        if action == "drills":
            return _drills()
        if action == "simulate":
            return _simulate()
        if action == "preflight":
            return _preflight(args)
        if action == "promotions":
            return _promotions(args)
        if action == "promote":
            return _promote(args)
        if action == "outcomes":
            return _outcomes(args)
        if action == "packs":
            return _packs()
        if action == "snapshot":
            return _snapshot(args)
        if action == "activate":
            return _activate(args)
        if action == "rollback":
            return _rollback(args)
        return tool_error(_UNKNOWN_ACTION_ERROR, success=False)
    except ValueError as exc:
        return tool_error(_validation_error_message(exc), success=False)
    except Exception as exc:
        logger.exception("Governance OS action failed: %s", exc)
        return tool_error(_INTERNAL_ERROR, success=False)


def _status() -> str:
    from plugins.governance_os.operations import run_readiness_check

    report = run_readiness_check()
    return tool_result(
        success=report.ready,
        readiness=_readiness_payload(report),
    )


def _drills() -> str:
    from plugins.governance_os.drill import run_builtin_drills
    from plugins.governance_os.versioning import load_runtime_registry

    drills = tuple(run_builtin_drills(load_runtime_registry()))
    return tool_result(
        success=all(item.passed for item in drills),
        passed=all(item.passed for item in drills),
        drills=[asdict(item) for item in drills],
    )


def _simulate() -> str:
    from plugins.governance_os.simulator import run_simulation_suite
    from plugins.governance_os.versioning import load_runtime_registry

    simulations = tuple(run_simulation_suite(load_runtime_registry()))
    return tool_result(
        success=all(item.passed for item in simulations),
        passed=all(item.passed for item in simulations),
        simulations=[asdict(item) for item in simulations],
    )


def _preflight(args: dict[str, Any]) -> str:
    from plugins.governance_os.deployment_preflight import run_deployment_preflight

    report = run_deployment_preflight(
        target=str(args.get("target") or "gateway_restart"),
        test_receipts=args.get("test_receipts"),
        smoke_receipts=args.get("smoke_receipts"),
        config_checks=args.get("config_checks"),
        rollback_plan=str(args.get("rollback_plan") or ""),
    )
    payload = report.to_metadata()
    if not report.ready:
        return tool_error(
            _preflight_failure_message(report.failures),
            success=False,
            preflight=payload,
        )
    return tool_result(success=True, preflight=payload)


def _promotions(args: dict[str, Any]) -> str:
    from plugins.governance_os.promotion import find_promotion_candidates

    candidates = find_promotion_candidates(
        limit=_positive_int(args.get("limit"), default=100),
        min_recurrence=_positive_int(args.get("min_recurrence"), default=2),
    )
    return tool_result(
        success=True,
        count=len(candidates),
        candidates=[item.to_metadata() for item in candidates],
    )


def _promote(args: dict[str, Any]) -> str:
    from plugins.governance_os.promotion import (
        PromotionAction,
        PromotionCandidate,
        activate_promotion_candidate,
    )

    candidate = PromotionCandidate(
        playbook_key=str(args.get("playbook_key") or "").strip(),
        source_failure=str(args.get("source_failure") or "").strip(),
        recurrence_count=_positive_int(args.get("recurrence_count"), default=0),
        proposed_policy=str(args.get("proposed_policy") or "").strip(),
        evidence=_string_tuple(args.get("evidence")),
        tests_required=_string_tuple(args.get("tests_required")),
        rollback=str(args.get("rollback") or "").strip(),
    )
    action_value = str(args.get("promotion_action") or "").strip()
    if action_value not in _PROMOTION_ACTIONS:
        raise ValueError("promotion_action must be add_forbidden_tool, add_required_tool, or add_review_gate")
    action = cast(PromotionAction, action_value)
    activation = activate_promotion_candidate(
        candidate,
        action=action,
        value=str(args.get("value") or "").strip(),
        test_receipts=args.get("test_receipts"),
        tests_passed=_string_tuple(args.get("tests_passed")),
        reason=str(args.get("reason") or "governance_os_tool promote"),
    )
    return tool_result(success=True, activation=activation.to_metadata())


def _outcomes(args: dict[str, Any]) -> str:
    from plugins.governance_os.ledger import list_outcomes

    outcomes = list_outcomes(
        limit=_positive_int(args.get("limit"), default=20),
        playbook_key=str(args.get("playbook_key") or ""),
    )
    return tool_result(success=True, count=len(outcomes), outcomes=outcomes)


def _packs() -> str:
    from plugins.governance_os.domain_packs import list_domain_packs
    from plugins.governance_os.versioning import load_runtime_registry

    packs = tuple(list_domain_packs(load_runtime_registry()))
    passed = all(pack.coverage_passed for pack in packs)
    return tool_result(
        success=passed,
        passed=passed,
        packs=[pack.to_metadata() for pack in packs],
    )


def _snapshot(args: dict[str, Any]) -> str:
    from plugins.governance_os.versioning import load_runtime_registry, snapshot_registry

    snapshot = snapshot_registry(
        load_runtime_registry(),
        reason=str(args.get("reason") or "governance_os_tool snapshot"),
    )
    return tool_result(success=True, snapshot=snapshot.to_metadata())


def _activate(args: dict[str, Any]) -> str:
    from plugins.governance_os.versioning import activate_registry_snapshot

    snapshot_id = _required_snapshot_id(args)
    _require_registry_runtime_verification(args)
    activation = activate_registry_snapshot(
        snapshot_id,
        reason=str(args.get("reason") or "governance_os_tool activate"),
    )
    return tool_result(success=True, activation=activation.to_metadata())


def _rollback(args: dict[str, Any]) -> str:
    from plugins.governance_os.versioning import (
        find_promotion_rollback_link,
        rollback_registry_snapshot,
    )

    snapshot_id = _required_snapshot_id(args)
    if not find_promotion_rollback_link(snapshot_id):
        _require_registry_runtime_verification(args)
    activation = rollback_registry_snapshot(
        snapshot_id,
        reason=str(args.get("reason") or "governance_os_tool rollback"),
    )
    return tool_result(success=True, activation=activation.to_metadata())


def _require_registry_runtime_verification(args: dict[str, Any]) -> None:
    from plugins.governance_os.deployment_preflight import run_deployment_preflight

    report = run_deployment_preflight(
        target=str(args.get("target") or "gateway_restart"),
        test_receipts=args.get("test_receipts"),
        smoke_receipts=args.get("smoke_receipts"),
        config_checks=args.get("config_checks"),
        rollback_plan=str(args.get("rollback_plan") or ""),
    )
    if not report.ready:
        failures = "; ".join(report.failures)
        raise ValueError(f"runtime verification is required before registry activation: {failures}")


def _required_snapshot_id(args: dict[str, Any]) -> str:
    snapshot_id = str(args.get("snapshot_id") or "").strip()
    if not snapshot_id:
        raise ValueError("snapshot_id is required")
    return snapshot_id


def _validation_error_message(exc: ValueError) -> str:
    text = str(exc).casefold()
    if (
        "tests_passed" in text
        or "test_receipts" in text
        or "test receipts" in text
        or "required tests" in text
    ):
        return "프로모션을 적용하려면 필요한 검증 테스트 통과 내역이 필요합니다."
    if "runtime verification" in text or "registry activation" in text:
        return "스냅샷을 활성화하거나 롤백하려면 구조화된 검증 내역과 롤백 계획이 필요합니다."
    if "snapshot_id" in text:
        return "스냅샷 ID가 필요합니다."
    return "입력값을 확인해 주세요. 거버넌스 OS 작업에 필요한 정보가 부족합니다."


def _preflight_failure_message(failures: tuple[str, ...]) -> str:
    text = " ".join(failures)
    parts: list[str] = []
    if "test receipts" in text:
        parts.append("테스트 영수증")
    if "smoke receipts" in text:
        parts.append("스모크 영수증")
    if "config checks" in text:
        parts.append("설정 확인")
    if "rollback plan" in text:
        parts.append("롤백 계획")
    if "readiness" in text:
        parts.append("거버넌스 readiness")
    missing = ", ".join(parts) if parts else "필수 확인 항목"
    return f"재시작 전 preflight가 통과하지 않았습니다. {missing}을 확인해 주세요."


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    return (text,) if text else ()


def _readiness_payload(report: Any) -> dict[str, Any]:
    return {
        "ready": report.ready,
        "quality_score": report.quality_score,
        "registry_valid": report.registry_valid,
        "drills_passed": report.drills_passed,
        "simulator_passed": report.simulator_passed,
        "council_probe_passed": report.council_probe_passed,
        "risk_probe_passed": report.risk_probe_passed,
        "promotion_probe_passed": report.promotion_probe_passed,
        "promotion_tests_probe_passed": report.promotion_tests_probe_passed,
        "retry_probe_passed": report.retry_probe_passed,
        "retry_instruction_probe_passed": report.retry_instruction_probe_passed,
        "transform_ledger_probe_passed": report.transform_ledger_probe_passed,
        "final_delivery_probe_passed": report.final_delivery_probe_passed,
        "final_delivery_retry_probe_passed": report.final_delivery_retry_probe_passed,
        "final_delivery_repair_probe_passed": report.final_delivery_repair_probe_passed,
        "final_qa_repair_probe_passed": report.final_qa_repair_probe_passed,
        "self_harness_autonomy_probe_passed": report.self_harness_autonomy_probe_passed,
        "self_harness_runtime_feedback_probe_passed": (
            report.self_harness_runtime_feedback_probe_passed
        ),
        "evolution_rollback_probe_passed": report.evolution_rollback_probe_passed,
        "hook_probe_passed": report.hook_probe_passed,
        "manifest_probe_passed": report.manifest_probe_passed,
        "plugin_load_probe_passed": report.plugin_load_probe_passed,
        "auxiliary_instruction_probe_passed": report.auxiliary_instruction_probe_passed,
        "auxiliary_dispatcher_dataplane_probe_passed": (
            report.auxiliary_dispatcher_dataplane_probe_passed
        ),
        "auxiliary_reviewer_dataplane_probe_passed": (
            report.auxiliary_reviewer_dataplane_probe_passed
        ),
        "domain_packs_passed": report.domain_packs_passed,
        "rollback_status": report.rollback_status,
        "active_snapshot_id": report.active_snapshot_id,
        "failures": list(report.failures),
    }


def check_governance_os_requirements() -> bool:
    return True


registry.register(
    name="governance_os",
    toolset="governance",
    schema=GOVERNANCE_OS_SCHEMA,
    handler=lambda args, **kw: governance_os_tool(args),
    check_fn=check_governance_os_requirements,
    emoji="GOV",
)
