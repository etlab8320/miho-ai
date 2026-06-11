"""NEIS MHTML table ingestion tests for life-record data fidelity."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource


def _event(thread_id: str) -> MessageEvent:
    return MessageEvent(
        text="유가은 생기부 넣어줘",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-1",
            chat_id=thread_id,
            parent_chat_id="channel-1",
            guild_id="guild-1",
            chat_name=f"thread-{thread_id}",
        ),
    )


def _write_table_mhtml(path: Path) -> None:
    html = """
    <html><body>
    <div>유가은 님</div>
    <h1>학교생활기록부</h1>
    <section>1. 인적·학적사항<br>성명<br>유가은<br>주민등록번호<br>081005-*******<br>
    2024년 03월 01일 저현고등학교 제1학년 입학</section>
    <table><tr><th>학년</th><th>학과</th><th>반</th><th>번호</th><th>담임성명</th></tr>
    <tr><td>1</td><td></td><td>5</td><td>15</td><td>담임</td></tr>
    <tr><td>2</td><td></td><td>9</td><td>11</td><td>담임</td></tr></table>
    <table><tr><th>학년</th><th>수업일수</th><th>결석일수</th><th>지 각</th><th>조 퇴</th><th>결 과</th><th>특기사항</th></tr>
    <tr><th>질병</th><th>미인정</th><th>기타</th><th>질병</th><th>미인정</th><th>기타</th><th>질병</th><th>미인정</th><th>기타</th><th>질병</th><th>미인정</th><th>기타</th></tr>
    <tr><td>1</td><td>191</td><td>.</td><td>.</td><td>.</td><td>.</td><td>1</td><td>.</td><td>.</td><td>.</td><td>.</td><td>.</td><td>.</td><td>.</td><td></td></tr>
    <tr><td>2</td><td>191</td><td>.</td><td>.</td><td>.</td><td>1</td><td>.</td><td>.</td><td>.</td><td>.</td><td>.</td><td>.</td><td>.</td><td>.</td><td></td></tr></table>
    <h2>6. 창의적 체험활동상황</h2><table><tr><th>학년</th><th>영역</th><th>시간</th><th>특기사항</th></tr>
    <tr><td>1</td><td>자율활동</td><td>10</td><td>스포츠 윤리를 탐구함.</td></tr></table>
    <h2>7. 교과학습발달상황</h2>
    <table><tr><th>학기</th><th>교과</th><th>과목</th><th>학점수</th><th>원점수/과목평균(표준편차)</th><th>성취도(수강자수)</th><th>석차등급</th><th>비고</th></tr>
    <tr><td>1</td><td>국어</td><td>국어</td><td>4</td><td>72/69.2(15.5)</td><td>C(293)</td><td>5</td><td></td></tr>
    <tr><td>2</td><td>과학</td><td>과학탐구실험</td><td>1</td><td>98/86.7(11.8)</td><td>A(283)</td><td></td><td></td></tr></table>
    <table><tr><td>이수학점 합계</td><td>5</td><td></td></tr></table>
    <table><tr><th>세부능력 및 특기사항</th></tr>
    <tr><td>국어: 문법을 꾸준히 학습함. 과학탐구실험: 실험 결과를 논리적으로 설명함.</td></tr></table>
    <table><tr><th>학기</th><th>교과</th><th>과목</th><th>학점수</th><th>원점수/과목평균</th><th>성취도(수강자수)</th><th>성취도별 분포비율</th><th>비고</th></tr>
    <tr><td>1</td><td>사회</td><td>사회문제 탐구</td><td>3</td><td>94/80.1</td><td>A(110)</td><td>A(62.7) B(26.4) C(10.9)</td><td></td></tr></table>
    <table><tr><td>이수학점 합계</td><td>3</td><td></td></tr></table>
    <table><tr><th>세부능력 및 특기사항</th></tr>
    <tr><td>사회문제 탐구: 주제와 가설을 체계적으로 설정함.</td></tr></table>
    <table><tr><th>학기</th><th>교과</th><th>과목</th><th>학점수</th><th>성취도</th><th>비고</th></tr>
    <tr><td>1</td><td>체육</td><td>운동과 건강</td><td>2</td><td>A</td><td></td></tr></table>
    <table><tr><td>이수학점 합계</td><td>2</td><td></td></tr></table>
    <table><tr><th>세부능력 및 특기사항</th></tr>
    <tr><td>(1학기)운동과 건강: 팀 경기에서 협력적 태도를 보임.</td></tr></table>
    <h2>9. 행동특성 및 종합의견</h2><table><tr><th>학년</th><th>행동특성 및 종합의견</th></tr>
    <tr><td>1</td><td>성실하게 생활함.</td></tr></table>
    </body></html>
    """
    path.write_text(f"MIME-Version: 1.0\nContent-Type: text/html; charset=utf-8\n\n{html}", encoding="utf-8")


def _write_transfer_mhtml(path: Path) -> None:
    _write_table_mhtml(path)
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "2024년 03월 01일 저현고등학교 제1학년 입학",
        "2024년 03월 01일 송곡고등학교 제1학년 입학(2025년 05월 19일 전출)<br>2025년 05월 20일 명지고등학교 제2학년 전입학",
    )
    path.write_text(text, encoding="utf-8")


def test_neis_mhtml_tables_extract_full_name_and_rows(tmp_path) -> None:
    from plugins.life_record.mhtml_tables import extract_neis_mhtml_tables

    mhtml = tmp_path / "record.mht"
    _write_table_mhtml(mhtml)

    parsed = extract_neis_mhtml_tables(mhtml)

    assert parsed.extraction["identity"]["name"] == "유가은"
    assert parsed.extraction["identity"]["class_no"] == "9"
    assert parsed.extraction["identity"]["student_no"] == "11"
    assert len(parsed.extraction["grades"]) == 4
    assert len(parsed.extraction["notes"]) == 4
    assert parsed.extraction["attendance"][0]["late_unexcused"] == 1
    assert parsed.extraction["attendance"][1]["late_disease"] == 1
    assert parsed.table_count >= 11
    assert len(parsed.sections) >= 3


def test_neis_mhtml_tables_prefers_latest_transfer_school(tmp_path) -> None:
    from plugins.life_record.mhtml_tables import extract_neis_mhtml_tables

    mhtml = tmp_path / "transfer.mht"
    _write_transfer_mhtml(mhtml)

    parsed = extract_neis_mhtml_tables(mhtml)

    assert parsed.extraction["identity"]["school_name"] == "명지고등학교"


def test_mhtml_ingest_uses_original_mhtml_without_pdf_conversion(monkeypatch, tmp_path) -> None:
    from plugins.life_record.context import capture_gateway_context
    from plugins.life_record.tools import _ingest_pdf_tool_handler
    from plugins.life_record.utils import sha256_file
    import plugins.life_record.service as service_module

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    def _pdf_path_must_not_run(*_args, **_kwargs):
        raise AssertionError("text-rich MHTML must not be converted to PDF")

    monkeypatch.setattr(service_module, "create_text_pdf", _pdf_path_must_not_run)
    monkeypatch.setattr(service_module, "convert_mhtml_to_pdf", _pdf_path_must_not_run)
    monkeypatch.setattr(service_module, "extract_pdf", _pdf_path_must_not_run)
    monkeypatch.setattr(service_module, "render_page_images", _pdf_path_must_not_run)

    mhtml = tmp_path / "record.mht"
    _write_table_mhtml(mhtml)
    capture_gateway_context(_event("thread-mhtml-original-hash"))

    result = json.loads(_ingest_pdf_tool_handler({"pdf_path": str(mhtml)}))
    db_path = Path(result["db_path"])
    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT file_sha256, page_count, stored_pdf_path, metadata_json FROM student_documents").fetchone()
        attendance = conn.execute("SELECT late_disease, late_unexcused FROM attendance_records ORDER BY grade").fetchall()

    metadata = json.loads(row[3])
    assert row[0] == sha256_file(mhtml)
    assert row[1] == result["mhtml_table_count"]
    assert row[2].endswith("_original.mht")
    assert "processing_pdf_path" not in metadata
    assert attendance == [(0, 1), (1, 0)]


def test_mhtml_ingest_accepts_already_stored_original(monkeypatch, tmp_path) -> None:
    from plugins.life_record.service import ingest_life_record
    from plugins.life_record.utils import sha256_file
    import asyncio
    import plugins.life_record.service as service_module

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    def _pdf_path_must_not_run(*_args, **_kwargs):
        raise AssertionError("stored text-rich MHTML must not be converted to PDF")

    monkeypatch.setattr(service_module, "create_text_pdf", _pdf_path_must_not_run)
    monkeypatch.setattr(service_module, "convert_mhtml_to_pdf", _pdf_path_must_not_run)
    monkeypatch.setattr(service_module, "extract_pdf", _pdf_path_must_not_run)
    monkeypatch.setattr(service_module, "render_page_images", _pdf_path_must_not_run)

    bundle = tmp_path / "life_records"
    source_dir = bundle / "sources"
    source_dir.mkdir(parents=True)
    staged = tmp_path / "source.mht"
    _write_table_mhtml(staged)
    mhtml = source_dir / f"{sha256_file(staged)[:16]}_original.mht"
    mhtml.write_bytes(staged.read_bytes())

    result = asyncio.run(ingest_life_record(mhtml, bundle))

    assert result["stored_original_path"] == str(mhtml)
    assert result["stored_pdf_path"] == str(mhtml)


def test_mhtml_reingest_replaces_superseded_thread_and_central_rows(monkeypatch, tmp_path) -> None:
    from plugins.life_record.service import ingest_life_record
    import asyncio
    import plugins.life_record.service as service_module

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr(service_module, "extract_pdf", lambda _p: None)
    monkeypatch.setattr(service_module, "render_page_images", lambda *a, **k: [])

    bundle = tmp_path / "life_records"
    first = tmp_path / "first.mht"
    second = tmp_path / "second.mht"
    _write_table_mhtml(first)
    _write_table_mhtml(second)

    first_result = asyncio.run(ingest_life_record(first, bundle, source_thread="thread-1"))
    second_result = asyncio.run(ingest_life_record(second, bundle, source_thread="thread-1"))

    with sqlite3.connect(first_result["db_path"]) as conn:
        documents = conn.execute("SELECT id FROM student_documents").fetchall()
        notes = conn.execute("SELECT COUNT(*) FROM subject_special_notes").fetchone()[0]
    central_path = tmp_path / "life_records" / "central.sqlite3"
    with sqlite3.connect(central_path) as conn:
        central_notes = conn.execute("SELECT COUNT(*) FROM central_notes").fetchone()[0]

    assert [row[0] for row in documents] == [second_result["document_id"]]
    assert notes == 4
    assert central_notes == 4


def test_mhtml_reingest_removes_same_thread_transfer_duplicate(monkeypatch, tmp_path) -> None:
    from plugins.life_record.repository import connect_central
    from plugins.life_record.service import ingest_life_record
    import asyncio
    import plugins.life_record.service as service_module

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr(service_module, "extract_pdf", lambda _p: None)
    monkeypatch.setattr(service_module, "render_page_images", lambda *a, **k: [])

    bundle = tmp_path / "life_records"
    old = tmp_path / "old.mht"
    new = tmp_path / "new.mht"
    _write_table_mhtml(old)
    _write_transfer_mhtml(new)

    asyncio.run(ingest_life_record(old, bundle, source_thread="thread-1"))
    asyncio.run(ingest_life_record(new, bundle, source_thread="thread-1"))

    with connect_central(tmp_path / "life_records" / "central.sqlite3") as conn:
        rows = conn.execute("SELECT name, school_name FROM students").fetchall()

    assert [(row["name"], row["school_name"]) for row in rows] == [("유가은", "명지고등학교")]
