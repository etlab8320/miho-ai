"""Foundation contract tests for the Miho Governance Agent OS plugin."""

from __future__ import annotations

from plugins.governance_os.registry import load_builtin_registry


def test_builtin_registry_validates_core_roles_and_playbooks() -> None:
    registry = load_builtin_registry()

    assert registry.validate() == []
    assert registry.get_role("dispatcher").kind == "control"
    assert registry.get_role("result_reviewer").kind == "judge"

    playbook = registry.get_playbook("academy_hakjong_report")
    assert playbook.domain == "academy"
    assert "academy_hakjong_report_package" in playbook.required_tools
    assert "execute_code" in playbook.forbidden_tools
    assert "academy_result_reviewer" in playbook.review_gates


def test_builtin_registry_includes_general_domain_packs() -> None:
    registry = load_builtin_registry()

    assert registry.get_role("dev_domain_agent").kind == "domain"
    assert registry.get_role("research_domain_agent").kind == "domain"
    assert registry.get_role("discord_ops_agent").kind == "domain"
    assert registry.get_role("memory_domain_agent").kind == "domain"

    dev = registry.get_playbook("dev_code_update")
    research = registry.get_playbook("research_brief")
    discord = registry.get_playbook("discord_attachment_delivery")
    memory = registry.get_playbook("memory_policy_update")

    assert dev.domain == "dev"
    assert "tests_required" in dev.required_context
    assert "source_attribution" in research.required_context
    assert "media_tag" in discord.required_context
    assert memory.domain == "memory"
    assert memory.required_tools == ("memory",)
    assert "raw_sensitive_data" in memory.forbidden_tools
