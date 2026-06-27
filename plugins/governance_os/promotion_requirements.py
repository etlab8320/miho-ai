"""Focused test requirements for Governance OS promotion candidates."""

from __future__ import annotations

REQUIRED_PROMOTION_SAFETY_TESTS = (
    "tests/plugins/test_governance_os_promotion_activation.py",
    "tests/plugins/test_governance_os_versioning.py",
)
DEFAULT_PROMOTION_TESTS = (
    "tests/plugins/test_governance_os_policy.py",
    "tests/plugins/test_governance_os_review_retry.py",
)
PROMOTION_TESTS_BY_PLAYBOOK: dict[str, tuple[str, ...]] = {
    "academy_hakjong_report": ("tests/plugins/test_academy_result_reviewer.py",),
    "academy_practical_reco": (
        "tests/plugins/test_academy_result_reviewer.py",
        "tests/plugins/test_academy_practical_reco.py",
    ),
    "discord_attachment_delivery": (
        "tests/e2e/test_discord_governance_delivery.py",
        "tests/tools/test_media_delivery_contract_tool.py",
    ),
    "research_brief": ("tests/plugins/test_governance_os_council.py",),
    "memory_policy_update": ("tests/plugins/test_governance_os_simulator.py",),
}
PROMOTION_TESTS_BY_FAILURE: dict[str, tuple[str, ...]] = {
    "forbidden_tool": (
        "tests/plugins/test_governance_os_policy.py",
        "tests/plugins/test_governance_os_drills.py",
    ),
    "reviewer_missing": (
        "tests/plugins/test_governance_os_review_retry.py",
        "tests/plugins/test_governance_os_council.py",
    ),
}


def tests_required_for_candidate(playbook_key: str, failure: str) -> tuple[str, ...]:
    return _dedupe_tests(
        PROMOTION_TESTS_BY_PLAYBOOK.get(playbook_key, DEFAULT_PROMOTION_TESTS),
        PROMOTION_TESTS_BY_FAILURE.get(failure, ()),
        REQUIRED_PROMOTION_SAFETY_TESTS,
    )


def _dedupe_tests(*groups: tuple[str, ...]) -> tuple[str, ...]:
    tests: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for test_path in group:
            if test_path in seen:
                continue
            seen.add(test_path)
            tests.append(test_path)
    return tuple(tests)
