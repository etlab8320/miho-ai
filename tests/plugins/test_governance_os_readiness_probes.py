"""Readiness probe contracts for Governance OS."""

from __future__ import annotations

from plugins.governance_os.readiness_probes import run_readiness_probes
from plugins.governance_os.registry import load_builtin_registry


def test_readiness_probes_cover_runtime_hook_and_retry_contracts() -> None:
    result = run_readiness_probes(load_builtin_registry())

    assert result.council_probe_passed
    assert result.risk_probe_passed
    assert result.promotion_probe_passed
    assert result.promotion_tests_probe_passed
    assert result.retry_probe_passed
    assert result.retry_instruction_probe_passed
    assert result.transform_ledger_probe_passed
    assert result.final_delivery_probe_passed
    assert result.final_delivery_retry_probe_passed
    assert result.pdf_attachment_quality_loop_probe_passed
    assert result.self_harness_runtime_feedback_probe_passed
    assert result.evolution_rollback_probe_passed
    assert result.hook_probe_passed
    assert result.manifest_probe_passed
    assert result.plugin_load_probe_passed
    assert result.auxiliary_instruction_probe_passed
    assert result.auxiliary_dispatcher_dataplane_probe_passed
    assert result.auxiliary_reviewer_dataplane_probe_passed
    assert result.semantic_delivery_judge_dataplane_probe_passed
    assert result.routing_loop_probe_passed
    assert result.tool_contract_probe_passed
    assert result.academy_accuracy_probe_passed
    assert result.validation_loop_probe_passed
    assert result.failures == ()
