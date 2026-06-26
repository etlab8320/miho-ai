"""Readiness probes for model-facing tool contract coverage."""

from __future__ import annotations

from plugins.decision_twin.contract_schema import contract_schema_errors

from .registry import GovernanceRegistry
from .router_map import build_router_map


CRITICAL_TOOL_CONTRACTS = frozenset(
    {
        "academy_hakjong_report_package",
        "academy_practical_reco_all_candidates",
        "academy_practical_reco_package",
        "susi27_recommend_candidates",
        "susi27_score_calculate",
        "html_pdf_quality_gate",
        "media_delivery_contract",
        "academy_thread_roster_lookup",
        "life_record_summary",
    }
)


def tool_contract_probe_passed(registry: GovernanceRegistry) -> bool:
    return tool_contract_probe_failures(registry) == ()


def tool_contract_probe_failures(registry: GovernanceRegistry) -> tuple[str, ...]:
    route_map = build_router_map(registry)
    contracts = route_map.get("tool_contracts")
    if not isinstance(contracts, dict):
        return ("router map tool_contracts is not a mapping",)
    expected = {
        tool
        for playbook in registry.playbooks.values()
        for tool in (*playbook.required_tools, *playbook.forbidden_tools)
    }
    failures: list[str] = []
    missing = sorted(expected - set(contracts))
    if missing:
        failures.append(f"router map missing contracts: {', '.join(missing)}")
    for name in sorted(expected & set(contracts)):
        contract = contracts.get(name)
        if not isinstance(contract, dict):
            failures.append(f"{name}: contract is not a mapping")
            continue
        failures.extend(contract_schema_errors(name, contract))
    for name in sorted(CRITICAL_TOOL_CONTRACTS & set(contracts)):
        contract = contracts[name]
        if str(contract.get("kind") or "") != "tool":
            failures.append(f"{name}: critical tool is not a tool contract")
    if "reportlab" in contracts and contracts["reportlab"].get("kind") != "blocked_capability":
        failures.append("reportlab must be a blocked_capability contract")
    return tuple(failures)
