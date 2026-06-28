"""Package delivery contract tests for governed artifact tools."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.governance_os.registry import load_builtin_registry
from plugins.governance_os.result_transform import governance_transform_tool_result
from plugins.governance_os.review import evaluate_review_gate


def _patch_broken_auxiliary(monkeypatch) -> list[dict[str, object]]:
    import plugins.governance_os.review as review

    calls: list[dict[str, object]] = []

    def broken_auxiliary_reviewer(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        raise RuntimeError("provider offline")

    monkeypatch.setattr(review, "_call_auxiliary_reviewer", broken_auxiliary_reviewer)
    return calls


def _reviewed_academy_package(pdf: Path) -> str:
    return json.dumps(
        {
            "ok": True,
            "success": True,
            "semantic_review_required": True,
            "message": f"학종 PDF 생성·검증 통과. MEDIA:{pdf}",
            "file_path": str(pdf),
            "media_tag": f"MEDIA:{pdf}",
            "reviewer": {
                "name": "academy_result_reviewer",
                "status": "pass",
                "mode": "llm_subagent",
                "checked": ["레이아웃", "산식"],
            },
        },
        ensure_ascii=False,
    )


def _reviewed_sports_package(pdf: Path) -> str:
    return json.dumps(
        {
            "ok": True,
            "success": True,
            "message": f"운동분석 리포트 생성·검증 통과. MEDIA:`{pdf}`",
            "artifact_path": str(pdf),
            "pdf_path": str(pdf),
            "media_tag": f"MEDIA:`{pdf}`",
            "reviewer": {
                "name": "sports_performance_reviewer",
                "status": "pass",
                "checked": ["학생/종목/지표", "PDF 품질 게이트"],
            },
        },
        ensure_ascii=False,
    )


def test_review_gate_accepts_reviewed_academy_package_without_auxiliary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _patch_broken_auxiliary(monkeypatch)
    pdf = tmp_path / "hakjong.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")

    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        result=_reviewed_academy_package(pdf),
        auxiliary_review_policy="always",
    )

    assert outcome.status == "pass"
    assert outcome.reason == "package_delivery_contract_pass"
    assert calls == []


def test_transform_accepts_reviewed_academy_package_without_auxiliary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _patch_broken_auxiliary(monkeypatch)
    pdf = tmp_path / "hakjong.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")

    transformed = governance_transform_tool_result(
        tool_name="academy_hakjong_report_package",
        result=_reviewed_academy_package(pdf),
        governance_skip_ledger=True,
    )

    assert transformed is None
    assert calls == []


def test_reviewed_package_without_media_still_uses_auxiliary_fail_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _patch_broken_auxiliary(monkeypatch)
    pdf = tmp_path / "hakjong.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    payload = json.loads(_reviewed_academy_package(pdf))
    payload.pop("media_tag")

    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        result=json.dumps(payload, ensure_ascii=False),
        auxiliary_review_policy="always",
    )

    assert outcome.status == "fail"
    assert outcome.reason == "auxiliary_reviewer_unavailable"
    assert calls


def test_review_gate_accepts_reviewed_sports_package_without_auxiliary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    calls = _patch_broken_auxiliary(monkeypatch)
    pdf = tmp_path / "sports.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")

    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="sports_motion_analysis",
        tool_name="sports_motion_report_package",
        result=_reviewed_sports_package(pdf),
        auxiliary_review_policy="always",
    )

    assert outcome.status == "pass"
    assert outcome.reason == "package_delivery_contract_pass"
    assert calls == []
