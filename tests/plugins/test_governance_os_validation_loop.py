"""Validation loop contracts for Governance OS review closure."""

from __future__ import annotations

from plugins.governance_os.validation_loop import (
    ADVERSARIAL_VALIDATOR_TASK,
    evaluate_validation_loop,
)


def _receipt(name: str, kind: str) -> dict[str, object]:
    return {
        "name": name,
        "kind": kind,
        "status": "passed",
        "exit_code": 0,
        "command": f"pytest {name}",
        "evidence": f"{name} passed",
    }


def test_validation_loop_requires_live_smoke_and_independent_review(tmp_path) -> None:
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"%PDF-1.4\n%%EOF\n")

    report = evaluate_validation_loop(
        test_receipts=(
            _receipt("tests/plugins/test_focus.py", "focused_tests"),
            _receipt("tests/plugins/test_wider.py", "wider_gate"),
            _receipt("readiness", "runtime_readiness"),
        ),
        smoke_receipts=(
            {
                "name": "attachment artifact",
                "kind": "attachment_artifact_smoke",
                "status": "passed",
                "artifact_path": str(artifact),
                "media_tag": f"MEDIA:`{artifact}`",
                "evidence": "local artifact staged",
            },
        ),
        adversarial_reviews=(),
    )

    assert not report.ready
    assert report.score < 100
    assert "missing required smoke: live_gateway_smoke" in report.failures
    assert "missing independent adversarial review" in report.failures


def test_validation_loop_rejects_self_review_as_independent(tmp_path) -> None:
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"%PDF-1.4\n%%EOF\n")

    report = evaluate_validation_loop(
        test_receipts=(
            _receipt("tests/plugins/test_focus.py", "focused_tests"),
            _receipt("tests/plugins/test_wider.py", "wider_gate"),
            _receipt("readiness", "runtime_readiness"),
        ),
        smoke_receipts=(
            {
                "name": "gateway live-safe smoke",
                "kind": "live_gateway_smoke",
                "status": "passed",
                "mode": "live_safe",
                "evidence": "gateway process and hook path verified",
            },
            {
                "name": "attachment artifact",
                "kind": "attachment_artifact_smoke",
                "status": "passed",
                "artifact_path": str(artifact),
                "media_tag": f"MEDIA:`{artifact}`",
                "evidence": "local artifact staged",
            },
        ),
        adversarial_reviews=(
            {
                "reviewer": "builder",
                "task": ADVERSARIAL_VALIDATOR_TASK,
                "status": "passed",
                "score": 100,
                "independent": False,
                "findings": [],
            },
        ),
    )

    assert not report.ready
    assert "missing independent adversarial review" in report.failures


def test_validation_loop_rejects_missing_attachment_artifact(tmp_path) -> None:
    missing = tmp_path / "missing.pdf"

    report = evaluate_validation_loop(
        test_receipts=(
            _receipt("tests/plugins/test_focus.py", "focused_tests"),
            _receipt("tests/plugins/test_wider.py", "wider_gate"),
            _receipt("readiness", "runtime_readiness"),
        ),
        smoke_receipts=(
            {
                "name": "gateway live-safe smoke",
                "kind": "live_gateway_smoke",
                "status": "passed",
                "mode": "live_safe",
                "evidence": "gateway process and hook path verified",
            },
            {
                "name": "attachment artifact",
                "kind": "attachment_artifact_smoke",
                "status": "passed",
                "artifact_path": str(missing),
                "media_tag": f"MEDIA:`{missing}`",
                "evidence": "local artifact staged",
            },
        ),
        adversarial_reviews=(
            {
                "reviewer": "validator",
                "task": ADVERSARIAL_VALIDATOR_TASK,
                "status": "passed",
                "score": 100,
                "independent": True,
                "findings": [],
            },
        ),
    )

    assert not report.ready
    assert "attachment artifact smoke did not prove deliverable MEDIA artifact" in report.failures


def test_validation_loop_passes_with_full_required_evidence(tmp_path) -> None:
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"%PDF-1.4\n%%EOF\n")

    report = evaluate_validation_loop(
        test_receipts=(
            _receipt("tests/plugins/test_focus.py", "focused_tests"),
            _receipt("tests/plugins/test_wider.py", "wider_gate"),
            _receipt("readiness", "runtime_readiness"),
        ),
        smoke_receipts=(
            {
                "name": "gateway live-safe smoke",
                "kind": "live_gateway_smoke",
                "status": "passed",
                "mode": "live_safe",
                "evidence": "gateway process and hook path verified",
            },
            {
                "name": "attachment artifact",
                "kind": "attachment_artifact_smoke",
                "status": "passed",
                "artifact_path": str(artifact),
                "media_tag": f"MEDIA:`{artifact}`",
                "evidence": "local artifact staged",
            },
        ),
        adversarial_reviews=(
            {
                "reviewer": "validator",
                "task": ADVERSARIAL_VALIDATOR_TASK,
                "status": "passed",
                "score": 100,
                "independent": True,
                "findings": [],
            },
        ),
    )

    assert report.ready
    assert report.score == 100
    assert report.failures == ()
