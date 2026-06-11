from __future__ import annotations

import json
from pathlib import Path

from plugins.academy_ops import hakjong_report_contract as contract
from plugins.academy_ops.hakjong_report_tool import _hakjong_report_package_tool_handler


def _locked_html(student: str = "홍길동", university: str = "성균관대학교") -> str:
    pages = []
    pages.append(
        f"""
        <section class="page cover">
          <div class="brandline reportIdentity"><img class="logo"><span>학생·학부모 확인용</span></div>
          <div class="coverCenter">
            <div class="heroCard">{student} 학생 {university} 스포츠과학과 성균인재</div>
            <div class="coverMetrics">최근결과 평균등급 학생 평균등급</div>
            <div class="sectionDeck">
              <div class="card">지원 적합도</div><div class="card">핵심 강점</div>
            </div>
          </div>
          <div class="footer">맥스체대입시 일산교육원 학생부종합 지원전략 리포트</div>
        </section>
        """
    )
    for index in range(3):
        pages.append(
            f"""
            <section class="page">
              <div class="topbar"><img><span>0{index + 1}</span></div>
              <div class="sectionDeck">
                <div class="card">{student} {university} 스포츠과학과 성균인재 지원 판단</div>
                <div class="card">3학년 1학기 입력 전 과세특 세특 진로활동 행특 보완과 대학 학과 평가 요소 확인</div>
              </div>
              <div class="footer">맥스체대입시 일산교육원 학생부종합 지원전략 리포트</div>
            </section>
            """
        )
    return (
        "<html><head><style>:root{--max-ink:#111827;--max-paper:#fbfaf7;"
        "--max-accent:#1f4e79;--max-warm:#b45309}"
        "*{letter-spacing:0;word-break:keep-all;overflow-wrap:break-word}"
        ".brandline{}.coverCenter{}.heroCard{}.coverMetrics{}.topbar{}.footer{}"
        ".reportIdentity{}.sectionDeck{}.card{}</style></head><body class='maxReport'>"
        + "\n".join(pages)
        + "</body></html>"
    )


def _grade1_html(student: str = "홍길동", university: str = "성균관대학교") -> str:
    return _locked_html(student, university).replace(
        "3학년 1학기 입력 전 과세특 세특 진로활동 행특 보완과 대학 학과 평가 요소 확인",
        "상담에서 확인한 관심 학교생활 기반으로 생활기록부 시작 기록 설계와 대학 학과 평가 요소 연결",
    )


def _write_report_files(tmp_path: Path, html: str | None = None) -> tuple[Path, Path, list[str], str]:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text(html or _locked_html(), encoding="utf-8")
    pdf_path.write_bytes(b"%PDF-1.4\n")
    page_images = []
    for index in range(4):
        image = tmp_path / f"page-{index + 1}.png"
        image.write_bytes(b"x" * 12_000)
        page_images.append(str(image))
    contact = tmp_path / "contact-sheet.png"
    contact.write_bytes(b"x" * 12_000)
    return html_path, pdf_path, page_images, str(contact)


def _patch_pdf_tools(monkeypatch, *, pages: int = 4, width: float = 594.96, height: float = 841.92) -> None:
    monkeypatch.setattr(
        contract,
        "_pdf_info",
        lambda _path: {"pages": pages, "width": width, "height": height},
    )
    monkeypatch.setattr(
        contract,
        "_pdf_text",
        lambda _path: {
            "text": (
                "홍길동 성균관대학교 스포츠과학과 성균인재 "
                "맥스체대입시 일산교육원 최종 판단 지원 전략"
            )
        },
    )


def test_hakjong_report_package_returns_media_tag_when_contract_passes(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_pdf_tools(monkeypatch)
    html_path, pdf_path, page_images, contact_sheet = _write_report_files(tmp_path)

    result = json.loads(
        _hakjong_report_package_tool_handler(
            {
                "html_path": str(html_path),
                "pdf_path": str(pdf_path),
                "student_name": "홍길동",
                "university_name": "성균관대학교",
                "department_name": "스포츠과학과",
                "track_name": "성균인재",
                "student_stage": "grade3",
                "evidence_tools": ["life_record_lookup", "qualitative_profile"],
                "page_image_paths": page_images,
                "contact_sheet_path": contact_sheet,
            }
        )
    )

    assert result["ok"] is True
    assert result["media_tag"].startswith("MEDIA:")
    assert Path(result["file_path"]).is_file()
    assert Path(result["manifest_path"]).is_file()


def test_hakjong_report_package_rejects_non_locked_template(monkeypatch, tmp_path) -> None:
    _patch_pdf_tools(monkeypatch)
    html_path, pdf_path, page_images, contact_sheet = _write_report_files(
        tmp_path,
        "<html><body><section class='page'>MIHO AI 홍길동 성균관대학교</section></body></html>",
    )

    result = json.loads(
        _hakjong_report_package_tool_handler(
            {
                "html_path": str(html_path),
                "pdf_path": str(pdf_path),
                "student_name": "홍길동",
                "university_name": "성균관대학교",
                "student_stage": "grade3",
                "evidence_tools": ["life_record_lookup", "qualitative_profile"],
                "page_image_paths": page_images,
                "contact_sheet_path": contact_sheet,
            }
        )
    )

    assert result["ok"] is False
    assert "media_tag" not in result
    assert any("locked premium_hakjong_report" in error for error in result["errors"])


def test_hakjong_report_package_missing_artifacts_returns_generation_plan(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))

    result = json.loads(
        _hakjong_report_package_tool_handler(
            {
                "student_name": "홍길동",
                "university_name": "성균관대학교",
                "department_name": "스포츠과학과",
                "track_name": "성균인재",
                "student_stage": "grade3",
                "evidence_tools": ["life_record_lookup", "qualitative_profile"],
                "page_image_paths": [],
            }
        )
    )

    assert result["ok"] is False
    assert result["next_action"]["ask_user_for_paths"] is False
    assert "write_file" in result["next_action"]["steps"]
    assert "academy_hakjong_report_package" in result["next_action"]["steps"]
    assert result["draft_paths"]["html_path"].endswith(".html")
    assert result["draft_paths"]["pdf_path"].endswith(".pdf")


def test_hakjong_report_package_rejects_missing_source_evidence(monkeypatch, tmp_path) -> None:
    _patch_pdf_tools(monkeypatch)
    html_path, pdf_path, page_images, contact_sheet = _write_report_files(tmp_path)

    result = json.loads(
        _hakjong_report_package_tool_handler(
            {
                "html_path": str(html_path),
                "pdf_path": str(pdf_path),
                "student_name": "홍길동",
                "university_name": "성균관대학교",
                "department_name": "스포츠과학과",
                "track_name": "성균인재",
                "student_stage": "grade3",
                "evidence_tools": ["qualitative_profile"],
                "page_image_paths": page_images,
                "contact_sheet_path": contact_sheet,
            }
        )
    )

    assert result["ok"] is False
    assert any("life-record evidence" in error for error in result["errors"])


def test_hakjong_report_package_rejects_landscape_pdf(monkeypatch, tmp_path) -> None:
    _patch_pdf_tools(monkeypatch, width=841.92, height=594.96)
    html_path, pdf_path, page_images, contact_sheet = _write_report_files(tmp_path)

    result = json.loads(
        _hakjong_report_package_tool_handler(
            {
                "html_path": str(html_path),
                "pdf_path": str(pdf_path),
                "student_name": "홍길동",
                "university_name": "성균관대학교",
                "department_name": "스포츠과학과",
                "track_name": "성균인재",
                "student_stage": "grade3",
                "evidence_tools": ["life_record_lookup", "qualitative_profile"],
                "page_image_paths": page_images,
                "contact_sheet_path": contact_sheet,
            }
        )
    )

    assert result["ok"] is False
    assert any("landscape" in error for error in result["errors"])


def test_hakjong_report_package_rejects_ai_source_wording(monkeypatch, tmp_path) -> None:
    _patch_pdf_tools(monkeypatch)
    monkeypatch.setattr(
        contract,
        "_pdf_text",
        lambda _path: {
            "text": (
                "홍길동 성균관대학교 스포츠과학과 성균인재 맥스체대입시 일산교육원 "
                "홍길동 학생 생활기록부 데이터, 대학 공식 전형자료, 맥스 수시엔진 산출 데이터 기준으로 구성했다."
            )
        },
    )
    html_path, pdf_path, page_images, contact_sheet = _write_report_files(tmp_path)

    result = json.loads(
        _hakjong_report_package_tool_handler(
            {
                "html_path": str(html_path),
                "pdf_path": str(pdf_path),
                "student_name": "홍길동",
                "university_name": "성균관대학교",
                "department_name": "스포츠과학과",
                "track_name": "성균인재",
                "student_stage": "grade3",
                "evidence_tools": ["life_record_lookup", "qualitative_profile"],
                "page_image_paths": page_images,
                "contact_sheet_path": contact_sheet,
            }
        )
    )

    assert result["ok"] is False
    assert any("자료 기준" in error or "수시엔진" in error for error in result["errors"])


def test_hakjong_report_package_rejects_non_brand_css(monkeypatch, tmp_path) -> None:
    _patch_pdf_tools(monkeypatch)
    html = _locked_html().replace("letter-spacing:0", "letter-spacing:-.03em")
    html_path, pdf_path, page_images, contact_sheet = _write_report_files(tmp_path, html)

    result = json.loads(
        _hakjong_report_package_tool_handler(
            {
                "html_path": str(html_path),
                "pdf_path": str(pdf_path),
                "student_name": "홍길동",
                "university_name": "성균관대학교",
                "department_name": "스포츠과학과",
                "track_name": "성균인재",
                "student_stage": "grade3",
                "evidence_tools": ["life_record_lookup", "qualitative_profile"],
                "page_image_paths": page_images,
                "contact_sheet_path": contact_sheet,
            }
        )
    )

    assert result["ok"] is False
    assert any("negative_letter_spacing" in error for error in result["errors"])


def test_hakjong_report_package_rejects_wall_text_report(monkeypatch, tmp_path) -> None:
    _patch_pdf_tools(monkeypatch)
    long_text = "지원 전략 설명 " * 40
    html = _locked_html().replace("class=\"card\"", "class=\"plain\"", 6).replace(
        "지원 적합도",
        long_text,
    )
    html_path, pdf_path, page_images, contact_sheet = _write_report_files(tmp_path, html)

    result = json.loads(
        _hakjong_report_package_tool_handler(
            {
                "html_path": str(html_path),
                "pdf_path": str(pdf_path),
                "student_name": "홍길동",
                "university_name": "성균관대학교",
                "department_name": "스포츠과학과",
                "track_name": "성균인재",
                "student_stage": "grade3",
                "evidence_tools": ["life_record_lookup", "qualitative_profile"],
                "page_image_paths": page_images,
                "contact_sheet_path": contact_sheet,
            }
        )
    )

    assert result["ok"] is False
    assert any("report card count" in error for error in result["errors"])
    assert any("overlong text" in error for error in result["errors"])


def test_hakjong_report_package_allows_grade1_consultation_context(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))
    _patch_pdf_tools(monkeypatch)
    html_path, pdf_path, page_images, contact_sheet = _write_report_files(tmp_path, _grade1_html())

    result = json.loads(
        _hakjong_report_package_tool_handler(
            {
                "html_path": str(html_path),
                "pdf_path": str(pdf_path),
                "student_name": "홍길동",
                "university_name": "성균관대학교",
                "department_name": "스포츠과학과",
                "track_name": "성균인재",
                "student_stage": "grade1",
                "evidence_tools": ["consultation_note", "qualitative_profile"],
                "page_image_paths": page_images,
                "contact_sheet_path": contact_sheet,
            }
        )
    )

    assert result["ok"] is True
    assert result["checks"]["student_stage"] == "grade1"


def test_hakjong_report_package_rejects_grade1_with_wrong_stage_body(monkeypatch, tmp_path) -> None:
    _patch_pdf_tools(monkeypatch)
    html_path, pdf_path, page_images, contact_sheet = _write_report_files(tmp_path)

    result = json.loads(
        _hakjong_report_package_tool_handler(
            {
                "html_path": str(html_path),
                "pdf_path": str(pdf_path),
                "student_name": "홍길동",
                "university_name": "성균관대학교",
                "department_name": "스포츠과학과",
                "track_name": "성균인재",
                "student_stage": "grade1",
                "evidence_tools": ["consultation_note", "qualitative_profile"],
                "page_image_paths": page_images,
                "contact_sheet_path": contact_sheet,
            }
        )
    )

    assert result["ok"] is False
    assert any("grade1 report is missing" in error for error in result["errors"])


def test_hakjong_report_package_rejects_missing_student_stage(monkeypatch, tmp_path) -> None:
    _patch_pdf_tools(monkeypatch)
    html_path, pdf_path, page_images, contact_sheet = _write_report_files(tmp_path)

    result = json.loads(
        _hakjong_report_package_tool_handler(
            {
                "html_path": str(html_path),
                "pdf_path": str(pdf_path),
                "student_name": "홍길동",
                "university_name": "성균관대학교",
                "department_name": "스포츠과학과",
                "track_name": "성균인재",
                "evidence_tools": ["life_record_lookup", "qualitative_profile"],
                "page_image_paths": page_images,
                "contact_sheet_path": contact_sheet,
            }
        )
    )

    assert result["ok"] is False
    assert any("student_stage is required" in error for error in result["errors"])
