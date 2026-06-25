"""Tests for practical_reco_schema and practical_reco_tool."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from plugins.academy_ops.practical_reco_schema import validate_content
from plugins.academy_ops.practical_reco_tool import (
    _practical_reco_package_tool_handler,
    _render_html,
    _safe_stem,
    _unique_pair,
    _contract,
)
import plugins.academy_ops.hakjong_report_contract as contract


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _para() -> str:
    """Return a substantive body paragraph ≤ 230 chars."""
    return (
        "이 학생의 내신 환산점수와 실기 만점 합산이 전년도 최종합격선에 충분히 도달하므로 "
        "적극적으로 지원을 권장한다. 실기 종목 준비를 철저히 하면 합격 가능성이 높다."
    )


def _base_content() -> dict:
    """Minimal valid content dict matching practical_reco_shell.html schema."""
    para = _para()
    return {
        "student": {
            "name": "홍길동",
            "avg_grade": "3.2",
            "basis_label": "생기부 내신 기준",
        },
        "title_lines": ["홍길동 학생", "수시 실기전형 추천 리포트"],
        "badge": {"line1": "상향 2", "line2": "적정 3"},
        "cover": {
            "pills": ["실기전형", "5개교 추천"],
            "key_judgment": {
                "headline": "실기 만점 시 전년도 최종합격선 도달 가능",
                "body": para,
            },
            "metrics": [
                {"label": "내신환산점수", "value": "312.5"},
                {"label": "실기만점 합산", "value": "412.5"},
                {"label": "추천 학교 수", "value": "5개교"},
            ],
        },
        "comparison": {
            "note": "전년도 결과 기준",
            "rows": [
                {
                    "school": "한국체육대학교",
                    "department": "체육학과",
                    "track": "실기우수자",
                    "converted": "312.5",
                    "max_total": "412.5",
                    "first_cut": "380.0",
                    "final_cut": "390.0",
                    "verdict": "상향",
                },
                {
                    "school": "서울대학교사범대학부속체육학교",
                    "department": "체육교육과",
                    "track": "실기",
                    "converted": "312.5",
                    "max_total": "412.5",
                    "first_cut": "300.0",
                    "final_cut": "310.0",
                    "verdict": "적정",
                },
            ],
        },
        "schools": [
            {
                "name": "한국체육대학교",
                "department": "체육학과",
                "track": "실기우수자",
                "verdict": "상향",
                "numbers": [
                    {"label": "내신환산", "value": "312.5"},
                    {"label": "실기만점 합산", "value": "412.5"},
                    {"label": "전년도 최초합", "value": "380.0"},
                    {"label": "전년도 최종합", "value": "390.0"},
                ],
                "events": ["100m", "제자리멀리뛰기"],
                "rationale_paragraphs": [para],
                "caution": "",
            },
            {
                "name": "서울대학교사범대학부속체육학교",
                "department": "체육교육과",
                "track": "실기",
                "verdict": "적정",
                "numbers": [
                    {"label": "내신환산", "value": "312.5"},
                    {"label": "실기만점 합산", "value": "412.5"},
                    {"label": "전년도 최초합", "value": "300.0"},
                    {"label": "전년도 최종합", "value": "310.0"},
                ],
                "events": ["농구"],
                "rationale_paragraphs": [para],
                "caution": "",
            },
        ],
        "final": {
            "cards": [
                {"title": "지원 전략 요약", "body": para},
                {"title": "실기 준비 포인트", "body": para},
                {"title": "일정 관리", "body": para},
            ],
            "callout": {
                "title": "선생님 최종 의견",
                "paragraphs": [para],
            },
            "tags": ["실기전형", "상향지원", "적정지원"],
        },
        "footnote": "산출 근거: 맥스 수시엔진 검증 룰 · 전년도 입시결과",
    }


def _base_args() -> dict:
    return {
        "student_name": "홍길동",
        "evidence_tools": ["susi27_recommend_candidates"],
        "content": _base_content(),
    }


_all_strings_cache: dict = {}


def _flatten_strings(obj) -> str:
    if isinstance(obj, str):
        return " " + obj
    if isinstance(obj, dict):
        return "".join(_flatten_strings(v) for v in obj.values())
    if isinstance(obj, list):
        return "".join(_flatten_strings(v) for v in obj)
    return ""


def _patch_pdf_tools(monkeypatch, *, width: float = 594.96, height: float = 841.92, content=None) -> None:
    # 잘림 검증(truncation_errors)은 content 전 문장이 PDF 텍스트에 있길 요구한다 —
    # 스텁도 content를 그대로 "인쇄"한 것으로 취급한다.
    _all_strings_cache["text"] = _flatten_strings(content) if content else ""
    monkeypatch.setattr(
        _contract,
        "_pdf_info",
        lambda _path: {"pages": 4, "width": width, "height": height},
    )
    monkeypatch.setattr(
        _contract,
        "_pdf_text",
        lambda _path: {"text": "홍길동 한국체육대학교 체육학과 맥스체대입시 일산교육원" + _all_strings_cache.get("text", "")},
    )


def _patch_recalc_ok(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_tool.validate_recalculated_scores",
        lambda _student_name, content: (
            True,
            [],
            {"recalculated_rows": len(((content.get("comparison") or {}).get("rows") or []))},
        ),
    )


def _fake_chromium(html_path: Path, pdf_path: Path) -> None:
    """Write a minimal valid PDF so physical checks don't error on missing file."""
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R 4 0 R]/Count 2>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"4 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"xref\n0 5\n"
        b"0000000000 65535 f\n"
        b"0000000009 00000 n\n"
        b"0000000074 00000 n\n"
        b"0000000133 00000 n\n"
        b"0000000214 00000 n\n"
        b"trailer<</Size 5/Root 1 0 R>>\n"
        b"startxref\n295\n%%EOF\n"
    )
    pdf_path.write_bytes(pdf_content)


def test_truncation_errors_accepts_ampersand_split_event_text() -> None:
    content = {"events": "제자리멀리뛰기, 20m왕복달리기, 농구(드리블 후 레이업슛&골밑슛)"}
    pdf_text = "제자리멀리뛰기 20m왕복달리기 농구 드리블 후 레이업슛 골밑슛"
    errors: list[str] = []

    _contract.truncation_errors(content, pdf_text, errors)

    assert errors == []


# ---------------------------------------------------------------------------
# Schema: valid content passes
# ---------------------------------------------------------------------------

def test_valid_content_passes() -> None:
    ok, errors = validate_content(_base_content(), evidence_tools=["susi27_recommend_candidates"])
    assert ok is True, errors


# ---------------------------------------------------------------------------
# Schema: verdict 오타 반려
# ---------------------------------------------------------------------------

def test_verdict_typo_rejected() -> None:
    content = _base_content()
    content["comparison"]["rows"][0]["verdict"] = "상향지원"  # 오타
    ok, errors = validate_content(content)
    assert ok is False
    assert any("verdict" in e for e in errors)


def test_verdict_school_typo_rejected() -> None:
    content = _base_content()
    content["schools"][0]["verdict"] = "안전"  # 허용 안 됨
    ok, errors = validate_content(content)
    assert ok is False
    assert any("verdict" in e for e in errors)


# ---------------------------------------------------------------------------
# Schema: rows-schools 불일치 반려
# ---------------------------------------------------------------------------

def test_rows_schools_length_mismatch_rejected() -> None:
    content = _base_content()
    # Remove one school while keeping two rows
    content["schools"] = content["schools"][:1]
    ok, errors = validate_content(content)
    assert ok is False
    assert any("길이" in e for e in errors)


def test_too_many_rows_rejected() -> None:
    content = _base_content()
    row = content["comparison"]["rows"][0].copy()
    school = content["schools"][0].copy()
    # Push beyond 8
    content["comparison"]["rows"] = [row] * 9
    content["schools"] = [school] * 9
    ok, errors = validate_content(content)
    assert ok is False
    assert any("8개" in e for e in errors)


# ---------------------------------------------------------------------------
# Schema: 수치 누락 반려
# ---------------------------------------------------------------------------

def test_missing_converted_rejected() -> None:
    content = _base_content()
    content["comparison"]["rows"][0]["converted"] = ""
    ok, errors = validate_content(content)
    assert ok is False
    assert any("converted" in e for e in errors)


def test_missing_final_cut_rejected() -> None:
    content = _base_content()
    content["comparison"]["rows"][0]["final_cut"] = "   "
    ok, errors = validate_content(content)
    assert ok is False
    assert any("final_cut" in e for e in errors)


# ---------------------------------------------------------------------------
# Schema: 품질 검증
# ---------------------------------------------------------------------------

def test_short_total_text_fails() -> None:
    content = _base_content()
    # Replace all rationale paragraphs with one-char strings
    for s in content["schools"]:
        s["rationale_paragraphs"] = ["짧"]
    content["cover"]["key_judgment"]["body"] = "짧"
    content["final"]["callout"]["paragraphs"] = ["짧"]
    for c in content["final"]["cards"]:
        c["body"] = "짧"
    ok, errors = validate_content(content)
    assert ok is False
    assert any("800자" in e for e in errors)


def test_overlong_text_block_fails() -> None:
    content = _base_content()
    content["schools"][0]["rationale_paragraphs"] = ["긴 텍스트 " * 50]
    ok, errors = validate_content(content)
    assert ok is False
    assert any("230자" in e for e in errors)


def test_banned_wording_fails() -> None:
    content = _base_content()
    content["final"]["callout"]["paragraphs"] = ["프리미엄 전략으로 구성했다."]
    ok, errors = validate_content(content)
    assert ok is False
    assert any("프리미엄" in e for e in errors)


# ---------------------------------------------------------------------------
# Tool: ok 흐름 (subprocess mock)
# ---------------------------------------------------------------------------

def test_valid_content_returns_media_tag(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_pdf_tools(monkeypatch, content=_base_args()["content"])
    _patch_recalc_ok(monkeypatch)

    with patch(
        "plugins.academy_ops.practical_reco_tool._chromium_print_to_pdf",
        side_effect=_fake_chromium,
    ):
        result = json.loads(_practical_reco_package_tool_handler(_base_args()))

    assert result["ok"] is True, result.get("errors")
    assert result["media_tag"].startswith("MEDIA:")
    assert Path(result["file_path"]).is_file()
    assert Path(result["manifest_path"]).is_file()


def test_manifest_written_on_success(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_pdf_tools(monkeypatch, content=_base_args()["content"])
    _patch_recalc_ok(monkeypatch)

    with patch(
        "plugins.academy_ops.practical_reco_tool._chromium_print_to_pdf",
        side_effect=_fake_chromium,
    ):
        result = json.loads(_practical_reco_package_tool_handler(_base_args()))

    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["ok"] is True
    assert "홍길동" == manifest["student_name"]
    assert "한국체육대학교" in manifest["school_names"]


def test_no_susi_evidence_yields_warning(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_pdf_tools(monkeypatch, content=_base_args()["content"])
    _patch_recalc_ok(monkeypatch)

    args = _base_args()
    args["evidence_tools"] = []  # 수시 산출 도구 없음

    with patch(
        "plugins.academy_ops.practical_reco_tool._chromium_print_to_pdf",
        side_effect=_fake_chromium,
    ):
        result = json.loads(_practical_reco_package_tool_handler(args))

    # Warning, not error — still ok
    assert result["ok"] is True, result.get("errors")
    assert result["warnings"]
    assert any("susi27" in w for w in result["warnings"])


def test_split_susi_tools_without_recommend_pipeline_yields_warning(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_pdf_tools(monkeypatch, content=_base_args()["content"])
    _patch_recalc_ok(monkeypatch)

    args = _base_args()
    args["evidence_tools"] = ["susi27_score_calculate", "susi27_rule_lookup"]

    with patch(
        "plugins.academy_ops.practical_reco_tool._chromium_print_to_pdf",
        side_effect=_fake_chromium,
    ):
        result = json.loads(_practical_reco_package_tool_handler(args))

    assert result["ok"] is True, result.get("errors")
    assert any("susi27_recommend_candidates" in w for w in result["warnings"])


def test_recalc_mismatch_rejected_before_pdf_generation(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.academy_ops.practical_reco_tool.validate_recalculated_scores",
        lambda _student_name, _content: (
            False,
            ["comparison.rows[0]: 내신환산(converted)이 공식 산출값과 다르다."],
            {"recalculated_rows": 1},
        ),
    )
    with patch(
        "plugins.academy_ops.practical_reco_tool._chromium_print_to_pdf",
        side_effect=AssertionError("PDF 생성 전에 차단되어야 한다."),
    ):
        result = json.loads(_practical_reco_package_tool_handler(_base_args()))

    assert result["ok"] is False
    assert any("내신환산" in e for e in result["errors"])
    assert result["checks"]["recalculated_rows"] == 1


# ---------------------------------------------------------------------------
# Tool: 브랜드 누락 반려
# ---------------------------------------------------------------------------

def test_missing_brand_text_in_pdf_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_pdf_tools(monkeypatch)
    _patch_recalc_ok(monkeypatch)
    monkeypatch.setattr(
        contract,
        "_pdf_text",
        lambda _path: {"text": "홍길동 한국체육대학교"},  # 브랜드 텍스트 없음
    )

    with patch(
        "plugins.academy_ops.practical_reco_tool._chromium_print_to_pdf",
        side_effect=_fake_chromium,
    ):
        result = json.loads(_practical_reco_package_tool_handler(_base_args()))

    assert result["ok"] is False
    assert any("브랜드" in e or "맥스체대입시" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Tool: Chromium 실패
# ---------------------------------------------------------------------------

def test_chromium_failure_returns_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_recalc_ok(monkeypatch)

    with patch(
        "plugins.academy_ops.practical_reco_tool._chromium_print_to_pdf",
        side_effect=RuntimeError("브라우저 없음"),
    ):
        result = json.loads(_practical_reco_package_tool_handler(_base_args()))

    assert result["ok"] is False
    assert any("브라우저" in e or "PDF" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Render HTML sanity
# ---------------------------------------------------------------------------

def test_render_html_contains_brand_and_student(monkeypatch) -> None:
    with patch("plugins.academy_ops.practical_reco_tool.report_font_css", return_value=""), \
         patch("plugins.academy_ops.practical_reco_tool.academy_brand_logo_src", return_value="data:image/png;base64,abc"):
        html = _render_html(_base_content())
    assert "맥스체대입시 일산교육원" in html
    assert "홍길동" in html


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_safe_stem_removes_special_chars() -> None:
    stem = _safe_stem("홍길동", "실기전형추천")
    assert "홍길동" in stem
    assert "실기전형추천" in stem


def test_unique_pair_increments_on_collision(tmp_path) -> None:
    html = tmp_path / "report.html"
    pdf = tmp_path / "report.pdf"
    html.touch()
    pdf.touch()
    new_html, new_pdf = _unique_pair(html, pdf)
    assert new_html != html
    assert new_pdf != pdf
