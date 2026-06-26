"""Readiness probes for academy engine accuracy contracts."""

from __future__ import annotations

from typing import Any

from plugins.academy_ops.accuracy_contract import (
    academy_accuracy_matrix,
    build_accuracy_receipt,
    validate_accuracy_matrix,
    validate_accuracy_receipt,
)
from plugins.decision_twin.contracts import decision_tool_contracts
from miho_cli.plugins import discover_plugins
from tools.registry import discover_builtin_tools, registry as tool_registry

from .registry import GovernanceRegistry


_ACADEMY_ROLE = "academy_domain_agent"


def academy_accuracy_probe_failures(registry: GovernanceRegistry) -> list[str]:
    """Return failures proving academy engines are not yet accuracy-governed."""
    discover_builtin_tools()
    discover_plugins(force=True)
    failures: list[str] = []
    matrix = academy_accuracy_matrix()
    failures.extend(validate_accuracy_matrix(matrix))
    contracts = decision_tool_contracts()
    for engine in matrix:
        failures.extend(_engine_failures(engine, registry, contracts))
    return failures


def _engine_failures(
    engine: dict[str, Any],
    registry: GovernanceRegistry,
    contracts: dict[str, dict[str, Any]],
) -> list[str]:
    key = str(engine.get("key") or "")
    canonical_tool = str(engine.get("canonical_tool") or "")
    source_tools = [str(tool) for tool in engine.get("source_tools") or []]
    playbook_key = str(engine.get("playbook_key") or "")
    required_axes = [str(axis) for axis in engine.get("required_axes") or []]
    failures: list[str] = []
    failures.extend(_tool_contract_failures(key, canonical_tool, contracts))
    if tool_registry.get_entry(canonical_tool) is None and canonical_tool not in contracts:
        failures.append(f"{key}: canonical tool not registered: {canonical_tool}")
    failures.extend(_tool_registry_failures(key, source_tools, contracts))
    if playbook_key:
        failures.extend(_playbook_failures(key, canonical_tool, playbook_key, registry))
    failures.extend(_receipt_failures(key, source_tools, required_axes))
    return failures


def _tool_contract_failures(
    engine_key: str,
    canonical_tool: str,
    contracts: dict[str, dict[str, Any]],
) -> list[str]:
    contract = contracts.get(canonical_tool)
    if not isinstance(contract, dict):
        return [f"{engine_key}: missing decision tool contract for {canonical_tool}"]
    failures: list[str] = []
    for field in ("purpose", "requires"):
        if not contract.get(field):
            failures.append(f"{engine_key}: {canonical_tool} contract missing {field}")
    contract_text = str(contract)
    if engine_key == "susi_practical_all_candidates":
        required_terms = ("단일 파이프라인", "전체", "직접 만들지 말")
        failures.extend(_missing_terms(engine_key, canonical_tool, contract_text, required_terms))
    if engine_key == "susi_score_engine":
        required_terms = ("verified", "환산점수", "invent")
        failures.extend(_missing_terms(engine_key, canonical_tool, contract_text, required_terms))
    if engine_key == "jungsi_score_engine":
        required_terms = ("정시", "수능", "score")
        failures.extend(_missing_terms(engine_key, canonical_tool, contract_text, required_terms))
    if engine_key == "hakjong_report":
        required_terms = ("hakjong_qualitative_profile", "life_record", "manifest_version=2")
        failures.extend(_missing_terms(engine_key, canonical_tool, contract_text, required_terms))
    return failures


def _missing_terms(
    engine_key: str,
    canonical_tool: str,
    purpose: str,
    required_terms: tuple[str, ...],
) -> list[str]:
    return [
        f"{engine_key}: {canonical_tool} contract missing term {term}"
        for term in required_terms
        if term not in purpose
    ]


def _tool_registry_failures(
    engine_key: str,
    tool_names: list[str],
    contracts: dict[str, dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    for tool_name in sorted(set(tool_names)):
        if tool_registry.get_entry(tool_name) is None and tool_name not in contracts:
            failures.append(f"{engine_key}: tool not registered: {tool_name}")
    return failures


def _playbook_failures(
    engine_key: str,
    canonical_tool: str,
    playbook_key: str,
    registry: GovernanceRegistry,
) -> list[str]:
    playbook = registry.playbooks.get(playbook_key)
    if playbook is None:
        return [f"{engine_key}: missing governance playbook {playbook_key}"]
    failures: list[str] = []
    if canonical_tool not in playbook.required_tools:
        failures.append(f"{engine_key}: playbook does not require {canonical_tool}")
    if _ACADEMY_ROLE not in playbook.agent_chain:
        failures.append(f"{engine_key}: playbook does not route through academy domain agent")
    if "academy_result_reviewer" not in playbook.review_gates:
        failures.append(f"{engine_key}: playbook missing academy_result_reviewer gate")
    role = registry.roles.get(_ACADEMY_ROLE)
    if role is None:
        failures.append(f"{engine_key}: missing {_ACADEMY_ROLE}")
    elif canonical_tool not in role.allowed_tools:
        failures.append(f"{engine_key}: academy role does not allow {canonical_tool}")
    return failures


def _receipt_failures(
    engine_key: str,
    source_tools: list[str],
    required_axes: list[str],
) -> list[str]:
    pass_receipt = build_accuracy_receipt(
        engine_key=engine_key,
        source_tools=source_tools,
        gates={axis: True for axis in required_axes},
    )
    failures = [
        f"{engine_key}: {error}"
        for error in validate_accuracy_receipt(pass_receipt)
    ]
    if pass_receipt.get("status") != "pass":
        failures.append(f"{engine_key}: pass receipt did not pass")
    missing_axis = required_axes[0] if required_axes else ""
    fail_receipt = build_accuracy_receipt(
        engine_key=engine_key,
        source_tools=source_tools,
        gates={axis: axis != missing_axis for axis in required_axes},
    )
    if fail_receipt.get("status") != "fail":
        failures.append(f"{engine_key}: missing-axis receipt did not fail")
    if missing_axis and f"missing axis: {missing_axis}" not in fail_receipt.get("errors", []):
        failures.append(f"{engine_key}: missing-axis receipt lacked explicit error")
    return failures
