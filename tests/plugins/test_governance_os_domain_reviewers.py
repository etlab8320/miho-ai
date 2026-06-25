"""Domain reviewer contracts for generic Governance OS review gates."""

from __future__ import annotations

import json

from plugins.governance_os.registry import load_builtin_registry
from plugins.governance_os.review import evaluate_review_gate


def test_dev_review_requires_dev_reviewer_and_core_checks() -> None:
    registry = load_builtin_registry()

    outcome = evaluate_review_gate(
        registry,
        playbook_key="dev_code_update",
        tool_name="apply_patch",
        result=json.dumps(
            {
                "ok": True,
                "reviewer": {
                    "name": "dev_quality_review",
                    "status": "pass",
                    "checked": ["tests", "rollback"],
                },
            }
        ),
    )

    assert outcome.status == "pass"
    assert outcome.reason == "reviewer_pass"


def test_review_gate_rejects_wrong_domain_reviewer() -> None:
    registry = load_builtin_registry()

    outcome = evaluate_review_gate(
        registry,
        playbook_key="dev_code_update",
        tool_name="apply_patch",
        result=json.dumps(
            {
                "ok": True,
                "reviewer": {
                    "name": "academy_result_reviewer",
                    "status": "pass",
                    "checked": ["tests", "rollback"],
                },
            }
        ),
    )

    assert outcome.status == "fail"
    assert outcome.reason == "reviewer_unexpected"
    assert "후검증 담당" in outcome.message_ko


def test_research_review_requires_source_attribution_check() -> None:
    registry = load_builtin_registry()

    outcome = evaluate_review_gate(
        registry,
        playbook_key="research_brief",
        tool_name="web_search",
        result=json.dumps(
            {
                "ok": True,
                "reviewer": {
                    "name": "source_attribution_review",
                    "status": "pass",
                    "checked": [],
                },
            }
        ),
    )

    assert outcome.status == "fail"
    assert outcome.reason == "reviewer_missing_required_checks"
    assert "필수 검수" in outcome.message_ko


def test_discord_attachment_review_requires_delivery_checks() -> None:
    registry = load_builtin_registry()

    outcome = evaluate_review_gate(
        registry,
        playbook_key="discord_attachment_delivery",
        tool_name="media_delivery_contract",
        result=json.dumps(
            {
                "ok": True,
                "reviewer": {
                    "name": "attachment_delivery_review",
                    "status": "pass",
                    "checked": ["media_tag", "artifact_path"],
                },
            }
        ),
    )

    assert outcome.status == "pass"
    assert outcome.reason == "reviewer_pass"


def test_memory_review_requires_evidence_and_privacy_checks() -> None:
    registry = load_builtin_registry()

    outcome = evaluate_review_gate(
        registry,
        playbook_key="memory_policy_update",
        tool_name="memory",
        result=json.dumps(
            {
                "ok": True,
                "reviewer": {
                    "name": "memory_promotion_review",
                    "status": "pass",
                    "checked": ["evidence"],
                },
            }
        ),
    )

    assert outcome.status == "fail"
    assert outcome.reason == "reviewer_missing_required_checks"
    assert "privacy" in outcome.message_ko
