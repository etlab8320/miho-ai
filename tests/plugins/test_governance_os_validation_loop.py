"""Validation loop contracts for Governance OS review closure."""

from __future__ import annotations

from plugins.governance_os.validation_loop import (
    ADVERSARIAL_VALIDATOR_TASK,
    evaluate_validation_loop,
    run_adversarial_validator,
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


def test_validation_loop_rejects_synthetic_adversarial_review(tmp_path) -> None:
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

    assert not report.ready
    assert "missing independent adversarial review" in report.failures


def test_run_adversarial_validator_builds_llm_receipt(tmp_path) -> None:
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"%PDF-1.4\n%%EOF\n")
    calls: list[dict[str, object]] = []

    def fake_call_llm(**kwargs: object) -> str:
        calls.append(kwargs)
        return (
            '{"reviewer":"external_validator","status":"pass","score":100,'
            '"independent":true,"findings":[]}'
        )

    review = run_adversarial_validator(
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
        change_summary="validation loop hardening",
        call_llm=fake_call_llm,
        extract_content=lambda value: value,
    )

    assert calls and calls[0]["task"] == ADVERSARIAL_VALIDATOR_TASK
    assert review["llm_receipt"] is True
    assert review["transport"] == "auxiliary_llm"
    assert review["prompt_sha256"]

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
        adversarial_reviews=(review,),
    )

    assert report.ready
    assert report.score == 100
    assert report.smoke_mode == "live_safe"
    assert report.live_delivery_verified is False


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
                "llm_receipt": True,
                "transport": "auxiliary_llm",
                "prompt_sha256": "abc123",
                "findings": [],
            },
        ),
    )

    assert report.ready
    assert report.score == 100
    assert report.failures == ()
    assert report.smoke_mode == "live_safe"
    assert report.live_delivery_verified is False


def test_validation_loop_marks_real_live_discord_delivery(tmp_path) -> None:
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
                "name": "gateway live smoke",
                "kind": "live_gateway_smoke",
                "status": "passed",
                "mode": "live",
                "send_attempted": True,
                "sent": True,
                "evidence": "gateway sent a Discord smoke attachment",
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
                "llm_receipt": True,
                "transport": "auxiliary_llm",
                "prompt_sha256": "abc123",
                "findings": [],
            },
        ),
    )

    assert report.ready
    assert report.score == 100
    assert report.smoke_mode == "live"
    assert report.live_delivery_verified is True
