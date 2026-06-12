"""Tests for the T3 hakjong_report_tool (new JSON-in, PDF-out flow)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from plugins.academy_ops.hakjong_report_tool import (
    _hakjong_report_package_tool_handler,
    _render_html,
    _safe_stem,
    _unique_pair,
    _contract,
)
import plugins.academy_ops.hakjong_report_contract as contract


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _base_content() -> dict:
    """Generate valid T3 content JSON matching hakjong_report_shell.html schema."""
    return {
        "student": {"name": "홍길동"},
        "university": {
            "name": "성균관대학교",
            "department": "스포츠과학과",
            "college": "스포츠과학대학",
            "track": "성균인재전형",
        },
        "badge": {"grade": "평가등급 B", "action": "강점 보강"},
        "title_lines": ["홍길동 학생", "학종 지원전략 리포트"],
        "cover": {
            "pills": ["성균관대학교", "학종"],
            "key_judgment": {
                "headline": "핵심 전략: 세특 일관성 강조",
                "body": "이 학생의 3년 일관된 체육 관심과 스포츠과학 진로활동이 가장 강력한 강점입니다.",
            },
            "metrics": [
                {"label": "지원적합도", "value": "높음"},
                {"label": "강점", "value": "세특 일관성"},
                {"label": "보완", "value": "면접 준비"},
            ],
        },
        "track_section": {
            "heading": "전형 분석",
            "info_cards": [
                {"label": "모집 정원", "value": "25명", "sub": ""},
                {"label": "경쟁률", "value": "15.3:1", "sub": ""},
                {"label": "합격선", "value": "종로학원 예측", "sub": ""},
            ],
            "rows": [
                {"label": "전공적합성", "official": "필수", "judgment": "우수"},
                {"label": "학업역량", "official": "필수", "judgment": "우수"},
                {"label": "인성 및 태도", "official": "우수", "judgment": "보통"},
            ],
            "strong_points": {
                "title": "강점",
                "bullets": [
                    "3년 일관된 체육 관련 세특",
                    "진로활동과 세특의 탁월한 연계성",
                    "내신 성적 꾸준한 유지",
                ],
            },
            "caution_points": {
                "title": "보완점",
                "bullets": [
                    "면접 경험 및 준비 필요",
                    "과학 과목 심화 탐구 기록 보강",
                    "통계 분석 등 심화 연구 기록 추가",
                ],
            },
            "footnote": "성균관대학교 성균인재전형은 학생부종합평가에서 학교생활의 충실도를 중시하며 특히 전공 관련 세특과 진로활동의 일관성을 높게 평가합니다. 지원 가능성 판단 시 1학기 입력 전 보완 사항을 고려합니다.",
        },
        "diagnosis_section": {
            "heading": "학생부 종합 분석",
            "strength": {
                "headline": "강점: 일관된 진로 추구",
                "body": "세특과 진로활동에서 스포츠과학에 대한 관심이 명확하게 드러나고 있으며, 이는 학종 평가 과정에서 매우 긍정적인 요소이다. "
                        "3년간 체육 관련 교과에서 지속적으로 깊이 있는 활동을 보여줌으로써 전공에 대한 진정한 관심을 증명하고 있다.",
            },
            "risk": {
                "headline": "보완: 학업 내용의 깊이",
                "body": "탐구활동에서 더욱 심화된 연구 기록과 통계 분석 등을 보여줄 수 있다면 학업역량을 더욱 강하게 입증할 수 있을 것이다. "
                        "또한 과학 기초 과목에서의 성취도를 높이면 스포츠과학 전공 준비를 더욱 체계적으로 보여줄 수 있다.",
            },
            "rows": [
                {"area": "세특", "record": "3년간 체육 관심 유지, 스포츠경영/해부학 중심 탐구", "interpretation": "긍정적", "check": "O"},
                {"area": "진로", "record": "스포츠과학 전문가 목표, 진로활동에서 지속적 추구", "interpretation": "일관성 우수", "check": "O"},
                {"area": "행특", "record": "체육 동아리 활동, 교내 대회 참가", "interpretation": "적극적 참여", "check": "O"},
            ],
            "gauges": [
                {"label": "학업역량", "level": "높음", "note": "내신 평균 3.2, 수학·과학 우수", "tone": "green", "percent": 85},
                {"label": "전공적합성", "level": "높음", "note": "세특 일관성, 진로 선명성", "tone": "green", "percent": 82},
                {"label": "인성", "level": "보통", "note": "봉사활동 50시간, 학급임원 경험", "tone": "blue", "percent": 70},
            ],
            "footnote": "학생부 종합 분석 참고사항: 대학이 평가하는 전공적합성, 탐구 지속성, 학교생활 태도를 종합적으로 검토한 결과",
        },
        "strategy_section": {
            "heading": "지원 전략",
            "actions": [
                {
                    "title": "1단계: 기초 준비",
                    "body": "지원 동기를 명확히 정의하고 성균관대학교 스포츠과학과의 교육과정을 충분히 이해합니다.",
                },
                {
                    "title": "2단계: 심화 준비",
                    "body": "교수 세미나 참석과 관련 논문 읽기를 통해 전공 지식을 심화하고 진로 목표를 구체화합니다.",
                },
                {
                    "title": "3단계: 실전 준비",
                    "body": "3회 이상 모의면접을 실시하여 자신감을 높이고 지원 대학의 면접 유형을 이해합니다.",
                },
                {
                    "title": "4단계: 최종 점검",
                    "body": "자소서와 면접 답변을 재검토하여 일관성 있고 설득력 있는 답변을 준비합니다.",
                },
            ],
            "interview_rows": [
                {
                    "question": "성균관대학교 스포츠과학과를 선택한 특별한 이유는 무엇입니까?",
                    "point": "세특의 구체적 활동 예시를 들어 설명하고 전공 선택의 이유를 명확히 표현",
                },
                {
                    "question": "향후 진로 목표와 그것을 달성하기 위한 준비 과정은?",
                    "point": "스포츠과학 전문가로서의 구체적 직업 목표와 그를 위한 단계별 준비 계획 제시",
                },
                {
                    "question": "학교생활 중 가장 보람 있었던 경험은 무엇인가요?",
                    "point": "체육 관련 활동 경험을 토대로 도전 정신과 성취감을 표현",
                },
            ],
            "final_judgment": {
                "body": "이 학생은 세특의 일관성과 전공 적합도가 높으며, 충실한 학교생활 기록을 보여줍니다. 따라서 성균관대학교 스포츠과학과에 적극 지원할 것을 권장합니다.",
            },
            "checklist": {
                "title": "최종 체크리스트",
                "bullets": [
                    "자소서 내용 점검 및 최종 수정 완료",
                    "면접 예상 질문 답변 준비 완료",
                    "지원 서류 전체 제출 확인",
                    "원서 제출 마감일 확인 및 여유있게 제출",
                ],
                "tags": ["우선순위: 높음", "난이도: 중"],
            },
            "footnote": "면접에서는 세특의 연계성과 진로 목표의 구체성을 강조하고, 대학과 학과의 연결고리를 명확히 보여주어야 합니다. 학교와 학과의 교육과정이 개인의 진로 목표와 부합함을 설명하는 것이 중요합니다.",
        },
    }


def _base_args() -> dict:
    return {
        "student_name": "홍길동",
        "student_stage": "grade3",
        "evidence_tools": ["life_record_lookup", "qualitative_profile"],
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
        lambda _path: {"text": "홍길동 성균관대학교 스포츠과학과 맥스체대입시 일산교육원" + _all_strings_cache.get("text", "")},
    )


def _fake_chromium(html_path: Path, pdf_path: Path) -> None:
    """Write a valid minimal PDF so physical checks don't error on missing file."""
    # A minimal but valid PDF with 4 pages as expected by the validator
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R 4 0 R 5 0 R 6 0 R]/Count 4>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"4 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"5 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"6 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]>>endobj\n"
        b"xref\n0 7\n"
        b"0000000000 65535 f\n"
        b"0000000009 00000 n\n"
        b"0000000074 00000 n\n"
        b"0000000133 00000 n\n"
        b"0000000214 00000 n\n"
        b"0000000295 00000 n\n"
        b"0000000376 00000 n\n"
        b"trailer<</Size 7/Root 1 0 R>>\n"
        b"startxref\n457\n%%EOF\n"
    )
    pdf_path.write_bytes(pdf_content)


# ---------------------------------------------------------------------------
# Schema rejection test
# ---------------------------------------------------------------------------

def test_schema_rejection_returns_korean_errors() -> None:
    """Invalid content JSON must fail immediately with Korean error messages."""
    args = _base_args()
    # Omit required top-level sections to trigger multiple structure errors
    args["content"] = {"student": {"name": ""}}
    result = json.loads(_hakjong_report_package_tool_handler(args))
    assert result["ok"] is False
    assert result["errors"]
    # Errors must be Korean and specific
    full = " ".join(result["errors"])
    assert any(char >= "가" for char in full), "에러 메시지가 한국어가 아니다."
    assert any("student.name" in e or "university" in e or "badge" in e for e in result["errors"])


def test_schema_rejection_no_media_tag() -> None:
    args = _base_args()
    args["content"] = {}
    result = json.loads(_hakjong_report_package_tool_handler(args))
    assert result["ok"] is False
    assert "media_tag" not in result


# ---------------------------------------------------------------------------
# Happy path (Chromium and pdftotext mocked)
# ---------------------------------------------------------------------------

def test_valid_content_returns_media_tag(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_pdf_tools(monkeypatch, content=_base_args()["content"])

    with patch(
        "plugins.academy_ops.hakjong_report_tool._chromium_print_to_pdf",
        side_effect=_fake_chromium,
    ):
        result = json.loads(_hakjong_report_package_tool_handler(_base_args()))

    assert result["ok"] is True, result.get("errors")
    assert result["media_tag"].startswith("MEDIA:")
    assert Path(result["file_path"]).is_file()
    assert Path(result["manifest_path"]).is_file()


def test_manifest_written_on_success(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_pdf_tools(monkeypatch, content=_base_args()["content"])

    with patch(
        "plugins.academy_ops.hakjong_report_tool._chromium_print_to_pdf",
        side_effect=_fake_chromium,
    ):
        result = json.loads(_hakjong_report_package_tool_handler(_base_args()))

    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["ok"] is True
    assert "성균관대학교" in manifest["university_names"]


# ---------------------------------------------------------------------------
# PDF physical validation
# ---------------------------------------------------------------------------

def test_landscape_pdf_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_pdf_tools(monkeypatch, width=841.92, height=594.96)

    with patch(
        "plugins.academy_ops.hakjong_report_tool._chromium_print_to_pdf",
        side_effect=_fake_chromium,
    ):
        result = json.loads(_hakjong_report_package_tool_handler(_base_args()))

    assert result["ok"] is False
    assert any("가로" in e for e in result["errors"])


def test_missing_brand_text_in_pdf_rejected(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_pdf_tools(monkeypatch)
    monkeypatch.setattr(
        contract,
        "_pdf_text",
        lambda _path: {"text": "홍길동 성균관대학교 스포츠과학과"},  # no brand text
    )

    with patch(
        "plugins.academy_ops.hakjong_report_tool._chromium_print_to_pdf",
        side_effect=_fake_chromium,
    ):
        result = json.loads(_hakjong_report_package_tool_handler(_base_args()))

    assert result["ok"] is False
    assert any("브랜드" in e or "맥스체대입시" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Chromium failure
# ---------------------------------------------------------------------------

def test_chromium_failure_returns_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))

    with patch(
        "plugins.academy_ops.hakjong_report_tool._chromium_print_to_pdf",
        side_effect=RuntimeError("브라우저 없음"),
    ):
        result = json.loads(_hakjong_report_package_tool_handler(_base_args()))

    assert result["ok"] is False
    assert any("브라우저" in e or "PDF" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Stage / evidence validation (schema layer, no subprocess needed)
# ---------------------------------------------------------------------------

def test_missing_student_stage_rejected() -> None:
    args = _base_args()
    args["student_stage"] = ""
    result = json.loads(_hakjong_report_package_tool_handler(args))
    assert result["ok"] is False
    assert any("student_stage" in e for e in result["errors"])


def test_missing_life_record_evidence_rejected() -> None:
    args = _base_args()
    args["evidence_tools"] = ["qualitative_profile"]
    result = json.loads(_hakjong_report_package_tool_handler(args))
    assert result["ok"] is False
    assert any("life_record" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_safe_stem_removes_special_chars() -> None:
    stem = _safe_stem("홍길동", "성균관대학교", "스포츠과학과")
    assert "홍길동" in stem
    assert "성균관대학교" in stem


def test_unique_pair_increments_on_collision(tmp_path) -> None:
    html = tmp_path / "report.html"
    pdf = tmp_path / "report.pdf"
    html.touch()
    pdf.touch()
    new_html, new_pdf = _unique_pair(html, pdf)
    assert new_html != html
    assert new_pdf != pdf


def test_render_html_contains_brand_text() -> None:
    """Jinja2 render should embed brand text and student name."""
    from unittest.mock import patch as _patch
    with _patch("plugins.academy_ops.hakjong_report_tool.report_font_css", return_value=""), \
         _patch("plugins.academy_ops.hakjong_report_tool.academy_brand_logo_src", return_value="data:image/png;base64,abc"):
        html = _render_html(_base_content())
    assert "맥스체대입시 일산교육원" in html
    assert "홍길동" in html
    assert "성균관대학교" in html
