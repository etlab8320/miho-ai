"""Domain pack coverage for Governance OS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .registry import GovernanceRegistry


@dataclass(frozen=True)
class DomainPackStatus:
    domain: str
    domain_agent_key: str
    playbook_keys: tuple[str, ...] = field(default_factory=tuple)
    required_tools: tuple[str, ...] = field(default_factory=tuple)
    forbidden_tools: tuple[str, ...] = field(default_factory=tuple)
    review_gates: tuple[str, ...] = field(default_factory=tuple)
    coverage_passed: bool = False
    failures: tuple[str, ...] = field(default_factory=tuple)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "domain": self.domain,
            "domain_agent_key": self.domain_agent_key,
            "playbook_keys": list(self.playbook_keys),
            "required_tools": list(self.required_tools),
            "forbidden_tools": list(self.forbidden_tools),
            "review_gates": list(self.review_gates),
            "coverage_passed": self.coverage_passed,
            "failures": list(self.failures),
        }


def list_domain_packs(registry: GovernanceRegistry) -> list[DomainPackStatus]:
    domains = sorted({playbook.domain for playbook in registry.playbooks.values()})
    return [_build_pack_status(registry, domain) for domain in domains if domain]


def domain_packs_passed(registry: GovernanceRegistry) -> bool:
    return all(pack.coverage_passed for pack in list_domain_packs(registry))


def _build_pack_status(registry: GovernanceRegistry, domain: str) -> DomainPackStatus:
    playbooks = [
        playbook
        for playbook in registry.playbooks.values()
        if playbook.domain == domain
    ]
    domain_agent_key = _domain_agent_key(registry, domain)
    failures: list[str] = []
    if not domain_agent_key:
        failures.append(f"{domain} missing domain agent")

    playbook_keys = tuple(sorted(playbook.key for playbook in playbooks))
    required_tools = _unique_sorted(tool for playbook in playbooks for tool in playbook.required_tools)
    forbidden_tools = _unique_sorted(
        tool for playbook in playbooks for tool in playbook.forbidden_tools
    )
    review_gates = _unique_sorted(gate for playbook in playbooks for gate in playbook.review_gates)

    for playbook in playbooks:
        if domain_agent_key and domain_agent_key not in playbook.agent_chain:
            failures.append(f"{playbook.key} missing {domain_agent_key}")
        if not playbook.required_tools:
            failures.append(f"{playbook.key} missing required tools")
        if playbook.review_gates and "result_reviewer" not in playbook.agent_chain:
            failures.append(f"{playbook.key} missing result_reviewer")

    return DomainPackStatus(
        domain=domain,
        domain_agent_key=domain_agent_key,
        playbook_keys=playbook_keys,
        required_tools=required_tools,
        forbidden_tools=forbidden_tools,
        review_gates=review_gates,
        coverage_passed=not failures,
        failures=tuple(failures),
    )


def _domain_agent_key(registry: GovernanceRegistry, domain: str) -> str:
    candidates = [
        key
        for key, role in registry.roles.items()
        if role.kind == "domain" and (key == f"{domain}_agent" or key.startswith(f"{domain}_"))
    ]
    return sorted(candidates)[0] if candidates else ""


def _unique_sorted(values: Any) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip() for value in values if str(value).strip()}))
