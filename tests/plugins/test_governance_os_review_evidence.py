"""Evidence-seeking contracts for Governance OS reviewers."""

from __future__ import annotations

import json

from plugins.governance_os.registry import load_builtin_registry
from plugins.governance_os.review import evaluate_review_gate


def test_auxiliary_reviewer_receives_artifact_and_source_evidence(
    monkeypatch,
    tmp_path,
) -> None:
    import plugins.governance_os.review as review

    pdf_path = tmp_path / "report.pdf"
    html_path = tmp_path / "report.html"
    contact_sheet_path = tmp_path / "contact_sheet.png"
    manifest_path = tmp_path / "report.validation.json"
    source_path = tmp_path / "source.md"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
    html_path.write_text(
        "<html><body><h1>홍길동 실기 추천</h1><p>수도권 후보 2개</p></body></html>",
        encoding="utf-8",
    )
    contact_sheet_path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        b"\x00\x00\x04\xb0\x00\x00\x02X"
        b"\x08\x02\x00\x00\x00"
    )
    manifest_path.write_text(
        json.dumps(
            {
                "ok": True,
                "mode": "all_candidates",
                "student_name": "홍길동",
                "row_count": 2,
                "school_names": ["테스트대1", "테스트대2"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    source_path.write_text("## 국민대반\n- 박세영\n", encoding="utf-8")
    calls: list[dict[str, object]] = []

    def fake_auxiliary_reviewer(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "status": "pass",
            "checked": ["레이아웃", "산식"],
        }

    monkeypatch.setattr(review, "_call_auxiliary_reviewer", fake_auxiliary_reviewer)

    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_practical_recommendation",
        tool_name="academy_practical_reco_all_candidates",
        result=json.dumps(
            {
                "ok": True,
                "file_path": str(pdf_path),
                "html_path": str(html_path),
                "manifest_path": str(manifest_path),
                "contact_sheet_path": str(contact_sheet_path),
                "source_paths": [str(source_path)],
                "media_tag": f"MEDIA:{pdf_path}",
                "semantic_review_required": True,
                "reviewer": {
                    "name": "academy_result_reviewer",
                    "status": "pass",
                    "checked": ["레이아웃", "산식"],
                },
            },
            ensure_ascii=False,
        ),
    )

    assert outcome.status == "pass"
    assert calls
    evidence = calls[0]["evidence_bundle"]
    assert isinstance(evidence, dict)
    assert evidence["missing_paths"] == []
    assert evidence["paths"][str(pdf_path)]["exists"] is True
    assert evidence["paths"][str(pdf_path)]["suffix"] == ".pdf"
    assert evidence["paths"][str(source_path)]["line_count"] == 2
    assert evidence["json_manifests"][str(manifest_path)]["row_count"] == 2
    inspections = evidence["artifact_inspections"]
    assert inspections[str(pdf_path)]["kind"] == "pdf"
    assert inspections[str(pdf_path)]["opened"] is True
    assert inspections[str(html_path)]["kind"] == "html"
    assert "홍길동 실기 추천" in inspections[str(html_path)]["text_sample"]
    assert inspections[str(contact_sheet_path)]["kind"] == "image"
    assert inspections[str(contact_sheet_path)]["width"] == 1200
    assert inspections[str(contact_sheet_path)]["height"] == 600


def test_review_gate_retries_when_required_evidence_path_is_missing(tmp_path) -> None:
    missing_pdf = tmp_path / "missing.pdf"

    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_practical_recommendation",
        tool_name="academy_practical_reco_all_candidates",
        result=json.dumps(
            {
                "ok": True,
                "file_path": str(missing_pdf),
                "media_tag": f"MEDIA:{missing_pdf}",
                "semantic_review_required": True,
                "reviewer": {
                    "name": "academy_result_reviewer",
                    "status": "pass",
                    "checked": ["레이아웃", "산식"],
                    "evidence_required": True,
                },
            },
            ensure_ascii=False,
        ),
    )

    assert outcome.status == "retry_needed"
    assert outcome.reason == "review_evidence_missing"
    assert outcome.retry_tools == (
        "academy_practical_reco_package",
        "academy_practical_reco_all_candidates",
        "susi27_recommend_candidates",
    )
