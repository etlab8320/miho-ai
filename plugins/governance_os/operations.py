"""Operational readiness checks for Governance OS."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from .domain_packs import DomainPackStatus, list_domain_packs
from .drill import DrillResult, run_builtin_drills
from .readiness_probes import run_readiness_probes
from .registry import GovernanceRegistry
from .simulator import SimulationResult, run_simulation_suite
from .versioning import active_registry_path, load_runtime_registry, read_registry_snapshot


@dataclass(frozen=True)
class GovernanceReadinessReport:
    ready: bool
    quality_score: int
    registry_valid: bool
    drills_passed: bool
    simulator_passed: bool
    council_probe_passed: bool
    risk_probe_passed: bool
    promotion_probe_passed: bool
    promotion_tests_probe_passed: bool
    retry_probe_passed: bool
    retry_instruction_probe_passed: bool
    transform_ledger_probe_passed: bool
    final_delivery_probe_passed: bool
    final_delivery_retry_probe_passed: bool
    pdf_attachment_quality_loop_probe_passed: bool
    final_delivery_repair_probe_passed: bool
    final_qa_repair_probe_passed: bool
    self_harness_autonomy_probe_passed: bool
    self_harness_runtime_feedback_probe_passed: bool
    evolution_rollback_probe_passed: bool
    hook_probe_passed: bool
    manifest_probe_passed: bool
    plugin_load_probe_passed: bool
    auxiliary_instruction_probe_passed: bool
    auxiliary_dispatcher_dataplane_probe_passed: bool
    auxiliary_reviewer_dataplane_probe_passed: bool
    semantic_delivery_judge_dataplane_probe_passed: bool
    routing_loop_probe_passed: bool
    tool_contract_probe_passed: bool
    validation_loop_probe_passed: bool
    academy_accuracy_probe_passed: bool
    domain_packs_passed: bool
    rollback_status: str
    validation_loop_smoke_mode: str = ""
    live_discord_verified: bool = False
    full_system_ready: bool = False
    full_system_score: int = 0
    active_snapshot_id: str = ""
    failures: tuple[str, ...] = field(default_factory=tuple)
    drill_results: tuple[DrillResult, ...] = field(default_factory=tuple)
    simulation_results: tuple[SimulationResult, ...] = field(default_factory=tuple)
    domain_pack_results: tuple[DomainPackStatus, ...] = field(default_factory=tuple)


def run_readiness_check() -> GovernanceReadinessReport:
    failures: list[str] = []
    rollback_status, active_snapshot_id = _rollback_status()
    if rollback_status == "invalid_active_snapshot":
        failures.append("active registry snapshot pointer is invalid")

    registry = load_runtime_registry()
    registry_errors = registry.validate()
    if registry_errors:
        failures.extend(f"registry: {error}" for error in registry_errors)

    drill_results = tuple(run_builtin_drills(registry))
    failed_drills = [result for result in drill_results if not result.passed]
    for result in failed_drills:
        failures.append(f"drill {result.key}: expected {result.expected}, observed {result.observed}")

    simulation_results = tuple(run_simulation_suite(registry))
    failed_simulations = [result for result in simulation_results if not result.passed]
    for result in failed_simulations:
        failures.append(
            f"simulation {result.key}: expected {result.expected}, observed {result.observed}"
        )

    registry_valid = not registry_errors
    drills_passed = not failed_drills
    simulator_passed = not failed_simulations
    probe_results = run_readiness_probes(registry)
    failures.extend(probe_results.failures)

    domain_pack_results = tuple(list_domain_packs(registry))
    domain_packs_passed = all(pack.coverage_passed for pack in domain_pack_results)
    for pack in domain_pack_results:
        for failure in pack.failures:
            failures.append(f"domain pack {pack.domain}: {failure}")

    ready = (
        registry_valid
        and drills_passed
        and simulator_passed
        and probe_results.council_probe_passed
        and probe_results.risk_probe_passed
        and probe_results.promotion_probe_passed
        and probe_results.promotion_tests_probe_passed
        and probe_results.retry_probe_passed
        and probe_results.retry_instruction_probe_passed
        and probe_results.transform_ledger_probe_passed
        and probe_results.final_delivery_probe_passed
        and probe_results.final_delivery_retry_probe_passed
        and probe_results.pdf_attachment_quality_loop_probe_passed
        and probe_results.final_delivery_repair_probe_passed
        and probe_results.final_qa_repair_probe_passed
        and probe_results.self_harness_autonomy_probe_passed
        and probe_results.self_harness_runtime_feedback_probe_passed
        and probe_results.evolution_rollback_probe_passed
        and probe_results.hook_probe_passed
        and probe_results.manifest_probe_passed
        and probe_results.plugin_load_probe_passed
        and probe_results.auxiliary_instruction_probe_passed
        and probe_results.auxiliary_dispatcher_dataplane_probe_passed
        and probe_results.auxiliary_reviewer_dataplane_probe_passed
        and probe_results.semantic_delivery_judge_dataplane_probe_passed
        and probe_results.routing_loop_probe_passed
        and probe_results.tool_contract_probe_passed
        and probe_results.validation_loop_probe_passed
        and probe_results.academy_accuracy_probe_passed
        and domain_packs_passed
        and rollback_status != "invalid_active_snapshot"
    )
    quality_score = _quality_score(
        registry_valid=registry_valid,
        drills_passed=drills_passed,
        simulator_passed=simulator_passed,
        council_probe_passed=probe_results.council_probe_passed,
        risk_probe_passed=probe_results.risk_probe_passed,
        promotion_probe_passed=probe_results.promotion_probe_passed,
        promotion_tests_probe_passed=probe_results.promotion_tests_probe_passed,
        retry_probe_passed=probe_results.retry_probe_passed,
        retry_instruction_probe_passed=probe_results.retry_instruction_probe_passed,
        transform_ledger_probe_passed=probe_results.transform_ledger_probe_passed,
        final_delivery_probe_passed=probe_results.final_delivery_probe_passed,
        final_delivery_retry_probe_passed=probe_results.final_delivery_retry_probe_passed,
        pdf_attachment_quality_loop_probe_passed=(
            probe_results.pdf_attachment_quality_loop_probe_passed
        ),
        final_delivery_repair_probe_passed=probe_results.final_delivery_repair_probe_passed,
        final_qa_repair_probe_passed=probe_results.final_qa_repair_probe_passed,
        self_harness_autonomy_probe_passed=probe_results.self_harness_autonomy_probe_passed,
        self_harness_runtime_feedback_probe_passed=(
            probe_results.self_harness_runtime_feedback_probe_passed
        ),
        evolution_rollback_probe_passed=probe_results.evolution_rollback_probe_passed,
        hook_probe_passed=probe_results.hook_probe_passed,
        manifest_probe_passed=probe_results.manifest_probe_passed,
        plugin_load_probe_passed=probe_results.plugin_load_probe_passed,
        auxiliary_instruction_probe_passed=probe_results.auxiliary_instruction_probe_passed,
        auxiliary_dispatcher_dataplane_probe_passed=(
            probe_results.auxiliary_dispatcher_dataplane_probe_passed
        ),
        auxiliary_reviewer_dataplane_probe_passed=(
            probe_results.auxiliary_reviewer_dataplane_probe_passed
        ),
        semantic_delivery_judge_dataplane_probe_passed=(
            probe_results.semantic_delivery_judge_dataplane_probe_passed
        ),
        routing_loop_probe_passed=probe_results.routing_loop_probe_passed,
        tool_contract_probe_passed=probe_results.tool_contract_probe_passed,
        validation_loop_probe_passed=probe_results.validation_loop_probe_passed,
        academy_accuracy_probe_passed=probe_results.academy_accuracy_probe_passed,
        domain_packs_passed=domain_packs_passed,
        rollback_valid=rollback_status != "invalid_active_snapshot",
    )
    full_system_ready = ready and probe_results.validation_loop_live_required_ready
    full_system_score = min(quality_score, probe_results.validation_loop_live_required_score)
    return GovernanceReadinessReport(
        ready=ready,
        quality_score=quality_score,
        registry_valid=registry_valid,
        drills_passed=drills_passed,
        simulator_passed=simulator_passed,
        council_probe_passed=probe_results.council_probe_passed,
        risk_probe_passed=probe_results.risk_probe_passed,
        promotion_probe_passed=probe_results.promotion_probe_passed,
        promotion_tests_probe_passed=probe_results.promotion_tests_probe_passed,
        retry_probe_passed=probe_results.retry_probe_passed,
        retry_instruction_probe_passed=probe_results.retry_instruction_probe_passed,
        transform_ledger_probe_passed=probe_results.transform_ledger_probe_passed,
        final_delivery_probe_passed=probe_results.final_delivery_probe_passed,
        final_delivery_retry_probe_passed=probe_results.final_delivery_retry_probe_passed,
        pdf_attachment_quality_loop_probe_passed=(
            probe_results.pdf_attachment_quality_loop_probe_passed
        ),
        final_delivery_repair_probe_passed=probe_results.final_delivery_repair_probe_passed,
        final_qa_repair_probe_passed=probe_results.final_qa_repair_probe_passed,
        self_harness_autonomy_probe_passed=probe_results.self_harness_autonomy_probe_passed,
        self_harness_runtime_feedback_probe_passed=(
            probe_results.self_harness_runtime_feedback_probe_passed
        ),
        evolution_rollback_probe_passed=probe_results.evolution_rollback_probe_passed,
        hook_probe_passed=probe_results.hook_probe_passed,
        manifest_probe_passed=probe_results.manifest_probe_passed,
        plugin_load_probe_passed=probe_results.plugin_load_probe_passed,
        auxiliary_instruction_probe_passed=probe_results.auxiliary_instruction_probe_passed,
        auxiliary_dispatcher_dataplane_probe_passed=(
            probe_results.auxiliary_dispatcher_dataplane_probe_passed
        ),
        auxiliary_reviewer_dataplane_probe_passed=(
            probe_results.auxiliary_reviewer_dataplane_probe_passed
        ),
        semantic_delivery_judge_dataplane_probe_passed=(
            probe_results.semantic_delivery_judge_dataplane_probe_passed
        ),
        routing_loop_probe_passed=probe_results.routing_loop_probe_passed,
        tool_contract_probe_passed=probe_results.tool_contract_probe_passed,
        validation_loop_probe_passed=probe_results.validation_loop_probe_passed,
        academy_accuracy_probe_passed=probe_results.academy_accuracy_probe_passed,
        domain_packs_passed=domain_packs_passed,
        rollback_status=rollback_status,
        validation_loop_smoke_mode=probe_results.validation_loop_smoke_mode,
        live_discord_verified=probe_results.live_discord_verified,
        full_system_ready=full_system_ready,
        full_system_score=full_system_score,
        active_snapshot_id=active_snapshot_id,
        failures=tuple(failures),
        drill_results=drill_results,
        simulation_results=simulation_results,
        domain_pack_results=domain_pack_results,
    )


def _quality_score(
    *,
    registry_valid: bool,
    drills_passed: bool,
    simulator_passed: bool,
    council_probe_passed: bool,
    risk_probe_passed: bool,
    promotion_probe_passed: bool,
    promotion_tests_probe_passed: bool,
    retry_probe_passed: bool,
    retry_instruction_probe_passed: bool,
    transform_ledger_probe_passed: bool,
    final_delivery_probe_passed: bool,
    final_delivery_retry_probe_passed: bool,
    pdf_attachment_quality_loop_probe_passed: bool,
    final_delivery_repair_probe_passed: bool,
    final_qa_repair_probe_passed: bool,
    self_harness_autonomy_probe_passed: bool,
    self_harness_runtime_feedback_probe_passed: bool,
    evolution_rollback_probe_passed: bool,
    hook_probe_passed: bool,
    manifest_probe_passed: bool,
    plugin_load_probe_passed: bool,
    auxiliary_instruction_probe_passed: bool,
    auxiliary_dispatcher_dataplane_probe_passed: bool,
    auxiliary_reviewer_dataplane_probe_passed: bool,
    semantic_delivery_judge_dataplane_probe_passed: bool,
    routing_loop_probe_passed: bool,
    tool_contract_probe_passed: bool,
    validation_loop_probe_passed: bool,
    academy_accuracy_probe_passed: bool,
    domain_packs_passed: bool,
    rollback_valid: bool,
) -> int:
    checks = (
        registry_valid,
        drills_passed,
        simulator_passed,
        council_probe_passed,
        risk_probe_passed,
        promotion_probe_passed,
        promotion_tests_probe_passed,
        retry_probe_passed,
        retry_instruction_probe_passed,
        transform_ledger_probe_passed,
        final_delivery_probe_passed,
        final_delivery_retry_probe_passed,
        pdf_attachment_quality_loop_probe_passed,
        final_delivery_repair_probe_passed,
        final_qa_repair_probe_passed,
        self_harness_autonomy_probe_passed,
        self_harness_runtime_feedback_probe_passed,
        evolution_rollback_probe_passed,
        hook_probe_passed,
        manifest_probe_passed,
        plugin_load_probe_passed,
        auxiliary_instruction_probe_passed,
        auxiliary_dispatcher_dataplane_probe_passed,
        auxiliary_reviewer_dataplane_probe_passed,
        semantic_delivery_judge_dataplane_probe_passed,
        routing_loop_probe_passed,
        tool_contract_probe_passed,
        validation_loop_probe_passed,
        academy_accuracy_probe_passed,
        domain_packs_passed,
        rollback_valid,
    )
    passed = sum(1 for item in checks if item)
    return round((passed / len(checks)) * 100)


def _rollback_status() -> tuple[str, str]:
    path = active_registry_path()
    if not path.exists():
        return "builtin", ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        snapshot_id = str(raw.get("snapshot_id") or "")
        read_registry_snapshot(snapshot_id)
    except (OSError, ValueError, json.JSONDecodeError):
        return "invalid_active_snapshot", ""
    return "snapshot", snapshot_id
