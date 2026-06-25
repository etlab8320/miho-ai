"""Domain pack coverage tests for Governance OS."""

from __future__ import annotations

from plugins.governance_os.domain_packs import list_domain_packs
from plugins.governance_os.registry import load_builtin_registry, registry_from_mapping


def test_domain_packs_cover_general_and_academy_domains() -> None:
    packs = list_domain_packs(load_builtin_registry())

    by_domain = {pack.domain: pack for pack in packs}

    assert set(by_domain) == {"academy", "dev", "research", "discord_ops", "memory"}
    assert by_domain["academy"].domain_agent_key == "academy_domain_agent"
    assert by_domain["academy"].playbook_keys == (
        "academy_hakjong_report",
        "academy_practical_recommendation",
        "life_record_ingest",
        "susi_score_calculation",
    )
    assert by_domain["discord_ops"].required_tools == ("media_delivery_contract",)
    assert all(pack.coverage_passed for pack in packs)


def test_domain_pack_flags_playbook_missing_domain_agent() -> None:
    payload = load_builtin_registry().to_payload()
    payload["playbooks"]["research_brief"]["agent_chain"].remove("research_domain_agent")
    registry = registry_from_mapping(payload)

    packs = list_domain_packs(registry)
    research = next(pack for pack in packs if pack.domain == "research")

    assert not research.coverage_passed
    assert "research_brief missing research_domain_agent" in research.failures
