"""Model-facing router map for Governance OS playbooks and tools."""

from __future__ import annotations

from typing import Any

from plugins.decision_twin.contract_schema import blocked_capability_contract

from .registry import GovernanceRegistry


def build_router_map(registry: GovernanceRegistry) -> dict[str, Any]:
    """Return compact playbook/tool contracts for the LLM dispatcher."""
    tool_contracts = _tool_contracts()
    return {
        "schema": "miho-governance-router-map/v1",
        "instruction": (
            "Use this map semantically. Triggers are examples, not keyword-only rules. "
            "Select the playbook and required tools that best satisfy the user's job."
        ),
        "playbooks": {
            key: _playbook_payload(playbook)
            for key, playbook in sorted(registry.playbooks.items())
        },
        "tool_contracts": _required_tool_contracts(registry, tool_contracts),
    }


def _playbook_payload(playbook: Any) -> dict[str, Any]:
    return {
        "domain": playbook.domain,
        "trigger_examples": list(playbook.triggers),
        "required_context": list(playbook.required_context),
        "required_tools": list(playbook.required_tools),
        "forbidden_tools": list(playbook.forbidden_tools),
        "agent_chain": list(playbook.agent_chain),
        "review_gates": list(playbook.review_gates),
        "delivery_format": playbook.delivery_format,
        "retry_policy": playbook.retry_policy,
    }


def _required_tool_contracts(
    registry: GovernanceRegistry,
    contracts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    required = {tool for playbook in registry.playbooks.values() for tool in playbook.required_tools}
    forbidden = {tool for playbook in registry.playbooks.values() for tool in playbook.forbidden_tools}
    names = required | forbidden
    return {
        name: contracts.get(name) or blocked_capability_contract(name)
        for name in sorted(names)
    }


def _tool_contracts() -> dict[str, dict[str, Any]]:
    try:
        from plugins.decision_twin.contracts import decision_tool_contracts

        return decision_tool_contracts()
    except ImportError:
        return {}
