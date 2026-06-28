"""Repair-contract coverage for hakjong report package failures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import plugins.academy_ops.hakjong_report_tool as report_tool
from plugins.governance_os.result_transform import governance_transform_tool_result


def test_hakjong_missing_content_returns_repair_contract() -> None:
    result = json.loads(
        report_tool._hakjong_report_package_tool_handler(
            {"student_name": "김동하", "student_stage": "grade3"}
        )
    )

    assert result["ok"] is False
    assert result["retry_required"] is True
    assert result["final_response_allowed"] is False
    assert "academy_hakjong_report_package" in result["agent_instruction"]


def test_hakjong_repair_contract_does_not_record_reviewer_missing() -> None:
    raw = report_tool._hakjong_report_package_tool_handler(
        {"student_name": "김동하", "student_stage": "grade3"}
    )
    recorded: list[object] = []

    transformed = governance_transform_tool_result(
        tool_name="academy_hakjong_report_package",
        result=raw,
        governance_ledger_recorder=recorded.append,
    )

    assert transformed is None
    assert recorded == []


def test_hakjong_physical_validation_failure_returns_repair_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    content = {
        "student": {"name": "김동하"},
        "university": {"name": "대전대학교", "department": "스포츠건강재활학과"},
    }
    monkeypatch.setattr(report_tool, "_infer_stage_from_birth", lambda _name: None)
    monkeypatch.setattr(
        report_tool,
        "validate_content_with_checks",
        lambda *_args, **_kwargs: (True, [], {"visible_text_chars": 1800}),
    )
    monkeypatch.setattr(report_tool, "_grounding_errors", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(report_tool, "_render_html", lambda *_args, **_kwargs: "<html></html>")
    monkeypatch.setattr(
        report_tool,
        "_render_pdf_fit",
        lambda _content, _html, pdf, **_kwargs: pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        or "<html></html>",
    )
    monkeypatch.setattr(report_tool, "_university_names_from_content", lambda _content: ["대전대학교"])
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))

    def fail_physical(*_args, **kwargs) -> None:
        kwargs["errors"].append("footer가 하단 고정 위치에서 발견되지 않았다.")

    monkeypatch.setattr(report_tool, "_validate_pdf_physical", fail_physical)

    result = json.loads(
        report_tool._hakjong_report_package_tool_handler(
            {
                "student_name": "김동하",
                "student_stage": "grade3",
                "content": content,
            }
        )
    )

    assert result["ok"] is False
    assert result["retry_required"] is True
    assert result["final_response_allowed"] is False
    assert any("footer" in error for error in result["errors"])
