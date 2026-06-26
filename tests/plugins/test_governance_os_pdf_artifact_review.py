"""Governance review coverage for HTML-first PDF artifacts."""

from __future__ import annotations

import json

from plugins.governance_os.registry import load_builtin_registry
from plugins.governance_os.result_transform import governance_transform_tool_result
from plugins.governance_os.review import evaluate_review_gate


def _passed_pdf_gate_payload() -> str:
    return json.dumps(
        {
            "success": True,
            "artifact_path": "/tmp/report.pdf",
            "pdf_quality_gate": {"ok": True, "page_count": 2},
            "reviewer": {
                "name": "html_pdf_quality_review",
                "status": "pass",
                "checked": [
                    "html_source",
                    "pdf_rendered",
                    "metadata_scrubbed",
                    "contact_sheet",
                    "visual_review",
                ],
            },
        }
    )


def _pdf_gate_payload_without_visual_review() -> str:
    return json.dumps(
        {
            "success": True,
            "artifact_path": "/tmp/report.pdf",
            "pdf_quality_gate": {"ok": True, "page_count": 2},
            "reviewer": {
                "name": "html_pdf_quality_review",
                "status": "pass",
                "checked": [
                    "html_source",
                    "pdf_rendered",
                    "metadata_scrubbed",
                    "contact_sheet",
                ],
            },
        }
    )


def test_pdf_quality_gate_review_passes_designed_artifact_playbook() -> None:
    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="designed_pdf_artifact",
        tool_name="html_pdf_quality_gate",
        result=_passed_pdf_gate_payload(),
        auxiliary_review_policy="never",
    )

    assert outcome.status == "pass"
    assert outcome.reason == "reviewer_pass"
    assert outcome.gate_names == ("html_pdf_quality_review",)


def test_pdf_quality_gate_review_requires_visual_review_check() -> None:
    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="designed_pdf_artifact",
        tool_name="html_pdf_quality_gate",
        result=_pdf_gate_payload_without_visual_review(),
        auxiliary_review_policy="never",
    )

    assert outcome.status == "fail"
    assert outcome.reason == "reviewer_missing_required_checks"
    assert "visual_review" in outcome.message_ko


def test_pdf_quality_gate_result_is_self_reviewed(monkeypatch) -> None:
    import plugins.governance_os.review as review

    calls: list[dict[str, object]] = []

    def fake_auxiliary_reviewer(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "status": "pass",
            "checked": [
                "html_source",
                "pdf_rendered",
                "metadata_scrubbed",
                "contact_sheet",
                "visual_review",
            ],
        }

    monkeypatch.setattr(review, "_call_auxiliary_reviewer", fake_auxiliary_reviewer)

    transformed = governance_transform_tool_result(
        tool_name="html_pdf_quality_gate",
        result=_passed_pdf_gate_payload(),
    )

    assert transformed is None
    assert calls
    assert calls[0]["task"] == "miho_governance_reviewer_delivery"
