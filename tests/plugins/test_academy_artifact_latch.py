"""Current-turn artifact latch coverage for reviewed academy PDFs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agent.turn_context import begin_turn_context
from plugins.academy_ops import hakjong_report_tool, practical_reco_all_candidates, practical_reco_tool
from plugins.academy_ops.result_reviewer import review_tool_result


def test_hakjong_review_pass_reuses_current_turn_pdf(monkeypatch, tmp_path: Path) -> None:
    begin_turn_context("hakjong-turn")
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    monkeypatch.setenv("MIHO_ACADEMY_RESULT_REVIEWER_LLM", "0")
    monkeypatch.setattr(
        "plugins.academy_ops.result_reviewer.record_academy_review_outcome",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(hakjong_report_tool, "_infer_stage_from_birth", lambda _name: None)
    monkeypatch.setattr(
        hakjong_report_tool,
        "validate_content_with_checks",
        lambda *_args, **_kwargs: (
            True,
            [],
            {"evidence_tools": ["life_record_lookup"], "visible_text_chars": 1800},
        ),
    )
    monkeypatch.setattr(hakjong_report_tool, "_grounding_errors", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(hakjong_report_tool, "_render_html", lambda *_args, **_kwargs: "<html></html>")
    monkeypatch.setattr(hakjong_report_tool, "_validate_pdf_physical", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        hakjong_report_tool,
        "collect_pdf_checks",
        lambda _pdf: {"pages": 1, "printed_text_chars": 2000},
    )
    render_calls = {"count": 0}

    def render_pdf(_content: dict[str, Any], html: Path, pdf: Path, **_kwargs: Any) -> str:
        render_calls["count"] += 1
        html.write_text("<html></html>", encoding="utf-8")
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return "<html></html>"

    monkeypatch.setattr(hakjong_report_tool, "_render_pdf_fit", render_pdf)
    args = {
        "student_name": "김동하",
        "student_stage": "grade3",
        "evidence_tools": ["life_record_lookup", "hakjong_storm_prewrite"],
        "content": {
            "student": {"name": "김동하"},
            "university": {
                "name": "대전대",
                "department": "스포츠건강재활학과",
                "track": "혜화인재",
            },
        },
    }

    first = hakjong_report_tool._hakjong_report_package_tool_handler(args)
    reviewed = review_tool_result(
        tool_name="academy_hakjong_report_package",
        args=args,
        result=first,
    )
    second = hakjong_report_tool._hakjong_report_package_tool_handler(args)

    assert json.loads(reviewed)["reviewer"]["status"] == "pass"
    assert json.loads(second)["file_path"] == json.loads(reviewed)["file_path"]
    assert render_calls["count"] == 1


def test_practical_review_pass_reuses_current_turn_pdf(monkeypatch, tmp_path: Path) -> None:
    begin_turn_context("practical-turn")
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    monkeypatch.setenv("MIHO_ACADEMY_RESULT_REVIEWER_LLM", "0")
    monkeypatch.setattr(
        "plugins.academy_ops.result_reviewer.record_academy_review_outcome",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(practical_reco_tool, "validate_content", lambda *_args, **_kwargs: (True, []))
    monkeypatch.setattr(
        practical_reco_tool,
        "validate_recalculated_scores",
        lambda *_args, **_kwargs: (True, [], {}),
    )
    monkeypatch.setattr(practical_reco_tool, "_render_html", lambda _content: "<html></html>")
    monkeypatch.setattr(practical_reco_tool, "_validate_pdf_physical", lambda *_args, **_kwargs: None)
    render_calls = {"count": 0}

    def write_pdf(_html: Path, pdf: Path) -> None:
        render_calls["count"] += 1
        pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")

    monkeypatch.setattr(practical_reco_tool, "_chromium_print_to_pdf", write_pdf)
    args = _practical_args()

    first = practical_reco_tool._practical_reco_package_tool_handler(args)
    reviewed = review_tool_result(
        tool_name="academy_practical_reco_package",
        args=args,
        result=first,
    )
    second = practical_reco_tool._practical_reco_package_tool_handler(args)

    assert json.loads(reviewed)["reviewer"]["status"] == "pass"
    assert json.loads(second)["file_path"] == json.loads(reviewed)["file_path"]
    assert render_calls["count"] == 1


def test_all_candidates_review_pass_reuses_current_turn_pdf(monkeypatch, tmp_path: Path) -> None:
    begin_turn_context("all-candidates-turn")
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    monkeypatch.setenv("MIHO_ACADEMY_RESULT_REVIEWER_LLM", "0")
    monkeypatch.setattr(
        "plugins.academy_ops.result_reviewer.record_academy_review_outcome",
        lambda *_args, **_kwargs: None,
    )
    build_calls = {"count": 0}

    def build_content(_student_name: str, _region: str) -> dict[str, Any]:
        build_calls["count"] += 1
        return _all_candidates_content()

    monkeypatch.setattr(practical_reco_all_candidates, "build_all_candidates_content", build_content)
    monkeypatch.setattr(practical_reco_all_candidates, "_render_html", lambda _content: "<html></html>")
    monkeypatch.setattr(
        practical_reco_all_candidates,
        "_chromium_print_to_pdf",
        lambda _html, pdf: pdf.write_bytes(b"%PDF-1.4\n%%EOF\n"),
    )
    monkeypatch.setattr(
        practical_reco_all_candidates,
        "_validate_pdf_physical",
        lambda *_args, **_kwargs: None,
    )
    args = {"student_name": "김서연", "region": "수도권, 강원, 충청"}

    first = practical_reco_all_candidates._all_candidates_tool_handler(args)
    reviewed = review_tool_result(
        tool_name="academy_practical_reco_all_candidates",
        args=args,
        result=first,
    )
    second = practical_reco_all_candidates._all_candidates_tool_handler(args)

    assert json.loads(reviewed)["reviewer"]["status"] == "pass"
    assert json.loads(second)["file_path"] == json.loads(reviewed)["file_path"]
    assert build_calls["count"] == 1


def _practical_args() -> dict[str, Any]:
    return {
        "student_name": "김서연",
        "evidence_tools": ["susi27_recommend_candidates"],
        "content": {
            "comparison": {
                "rows": [
                    {"school": "대전대", "department": "스포츠건강재활학과", "track": "실기일반"},
                ],
            },
        },
    }


def _all_candidates_content() -> dict[str, Any]:
    return {
        "comparison": {
            "rows": [
                {"school": "대전대", "department": "스포츠건강재활학과", "track": "실기일반"},
            ],
        },
        "accuracy_receipt": {"ok": True},
    }
