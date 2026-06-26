"""Self-Harness shadow candidate contracts for Miho Governance OS."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from plugins.governance_os.self_harness import (
    build_evidence_bundle,
    build_shadow_candidates,
)
from plugins.governance_os.feedback_events import build_quality_failure_entry
from plugins.governance_os.self_harness_autonomy import (
    activate_autonomous_candidate,
    decide_autonomous_activation,
    rollback_on_regression,
)


def _event(event_id: int, *, playbook: str, failure: str, status: str = "fail") -> dict[str, object]:
    return {
        "id": event_id,
        "metadata": {
            "governance_outcome": {
                "request_id": f"req-{event_id}",
                "playbook_key": playbook,
                "review_status": status,
                "failures": [failure],
                "tools_used": ["media_delivery_contract"],
            }
        },
    }


def test_self_harness_mines_repeated_failures_without_active_write() -> None:
    bundle = build_evidence_bundle(
        [
            _event(1, playbook="discord_attachment_delivery", failure="reviewer_missing"),
            _event(2, playbook="discord_attachment_delivery", failure="reviewer_missing"),
            _event(3, playbook="susi_score_calculation", failure="one_off"),
        ],
        min_recurrence=2,
    )

    assert bundle["schema_version"] == "miho-self-harness/evidence-bundle/v1"
    assert bundle["canonical_write"] is False
    assert bundle["active_registry_write"] is False
    assert bundle["stage"] == "weakness_mining"
    assert bundle["pattern_count"] == 1
    [pattern] = bundle["patterns"]
    assert pattern["playbook_key"] == "discord_attachment_delivery"
    assert pattern["failure_signature"] == "reviewer_missing"
    assert pattern["recurrence_count"] == 2
    assert pattern["evidence"] == [
        "event=1 request_id=req-1 review_status=fail",
        "event=2 request_id=req-2 review_status=fail",
    ]


def test_self_harness_mines_user_feedback_quality_failures() -> None:
    entries = [
        build_quality_failure_entry(
            request_id=f"feedback-{index}",
            playbook_key="designed_pdf_artifact",
            failure_signature="pdf_footer_overflow",
            user_feedback="푸터가 아래로 밀려서 상담용 PDF로 쓰기 어렵다",
            artifact_paths=("/tmp/report.pdf",),
        )
        for index in (1, 2)
    ]
    events = [
        {
            "id": index,
            "metadata": {"governance_outcome": entry.to_metadata()},
        }
        for index, entry in enumerate(entries, start=1)
    ]

    bundle = build_evidence_bundle(events, min_recurrence=2)

    assert bundle["pattern_count"] == 1
    [pattern] = bundle["patterns"]
    assert pattern["playbook_key"] == "designed_pdf_artifact"
    assert pattern["failure_signature"] == "pdf_footer_overflow"
    assert pattern["target_surface_hint"] == "final_delivery_repair"
    assert "feedback=푸터가 아래로 밀려서 상담용 PDF로 쓰기 어렵다" in pattern["evidence"][0]


def test_self_harness_builds_shadow_candidates_only() -> None:
    bundle = build_evidence_bundle(
        [
            _event(1, playbook="discord_attachment_delivery", failure="attachment_delivery_failed"),
            _event(2, playbook="discord_attachment_delivery", failure="attachment_delivery_failed"),
        ],
        min_recurrence=2,
    )

    candidates = build_shadow_candidates(bundle)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["schema_version"] == "miho-self-harness/shadow-candidate/v1"
    assert candidate["status"] == "shadow_candidate"
    assert candidate["auto_promote_allowed"] is False
    assert candidate["target_surface"] == "final_delivery_repair"
    assert candidate["validation"]["held_in_required"] is True
    assert candidate["validation"]["held_out_required"] is True
    assert "rollback" in candidate


def test_self_harness_keeps_domain_reviewer_and_final_qa_surfaces_distinct() -> None:
    bundle = build_evidence_bundle(
        [
            _event(1, playbook="academy_hakjong_report", failure="reviewer_missing"),
            _event(2, playbook="academy_hakjong_report", failure="reviewer_missing"),
            _event(3, playbook="dev_code_update", failure="final_qa_revise"),
            _event(4, playbook="dev_code_update", failure="final_qa_revise"),
        ],
        min_recurrence=2,
    )

    candidates = build_shadow_candidates(bundle)
    by_failure = {item["source_pattern"]["failure_signature"]: item for item in candidates}

    assert by_failure["reviewer_missing"]["target_surface"] == "domain_reviewer_contract"
    assert by_failure["final_qa_revise"]["target_surface"] == "final_qa_agent"
    assert by_failure["reviewer_missing"]["target_surface"] != by_failure["final_qa_revise"]["target_surface"]

    validation = by_failure["final_qa_revise"]["validation"]
    assert isinstance(validation, dict)
    required_tests = validation["required_tests"]
    assert isinstance(required_tests, list)
    assert all(Path(str(test_name)).is_file() for test_name in required_tests)


def _passing_receipts(candidate: dict[str, object]) -> tuple[dict[str, object], ...]:
    validation = candidate["validation"]
    assert isinstance(validation, dict)
    typed_validation = cast("dict[str, object]", validation)
    required_tests = typed_validation["required_tests"]
    assert isinstance(required_tests, list)
    receipts: list[dict[str, object]] = []
    for test_name in required_tests:
        receipts.append(
            {
                "name": str(test_name),
                "status": "passed",
                "exit_code": 0,
                "command": f"pytest {test_name}",
                "evidence": f"{test_name} passed in self-harness autonomous loop",
            }
        )
    return tuple(receipts)


def _attachment_candidate() -> dict[str, object]:
    bundle = build_evidence_bundle(
        [
            _event(1, playbook="discord_attachment_delivery", failure="attachment_delivery_failed"),
            _event(2, playbook="discord_attachment_delivery", failure="attachment_delivery_failed"),
        ],
        min_recurrence=2,
    )
    [candidate] = build_shadow_candidates(bundle)
    return candidate


def test_self_harness_autonomous_decision_activates_after_receipts() -> None:
    candidate = _attachment_candidate()
    decision = decide_autonomous_activation(candidate, test_receipts=_passing_receipts(candidate))

    assert decision["action"] == "activate"
    assert decision["active_registry_write"] is True
    assert decision["user_approval_required"] is False
    assert decision["missing_tests"] == []
    assert decision["failed_tests"] == []
    assert decision["rollback_required"] is True


def test_self_harness_autonomous_decision_holds_without_held_out_receipt() -> None:
    candidate = _attachment_candidate()
    receipts = _passing_receipts(candidate)[:-1]
    decision = decide_autonomous_activation(candidate, test_receipts=receipts)

    assert decision["action"] == "hold"
    assert decision["active_registry_write"] is False
    assert decision["user_approval_required"] is False
    assert decision["missing_tests"]


def test_self_harness_autonomous_activation_writes_active_registry_and_rolls_back(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import importlib
    import miho_constants
    from agent import evolution

    importlib.reload(miho_constants)
    importlib.reload(evolution)

    from plugins.governance_os.versioning import load_runtime_registry

    candidate = _attachment_candidate()
    activation = activate_autonomous_candidate(
        candidate,
        test_receipts=_passing_receipts(candidate),
        created_at="2026-06-26T00:00:00+00:00",
    )
    runtime = load_runtime_registry()

    assert activation.value == "final_delivery_repair"
    assert "final_delivery_repair" in runtime.get_playbook("discord_attachment_delivery").review_gates
    assert activation.rollback_snapshot_id

    rollback = rollback_on_regression(
        activation,
        regression_receipts=(
            {
                "name": "tests/e2e/test_discord_governance_delivery.py",
                "status": "failed",
                "exit_code": 1,
                "command": "pytest tests/e2e/test_discord_governance_delivery.py",
                "evidence": "post-activation smoke failed",
            },
        ),
    )
    rolled_back = load_runtime_registry()

    assert rollback is not None
    assert "final_delivery_repair" not in rolled_back.get_playbook(
        "discord_attachment_delivery"
    ).review_gates
