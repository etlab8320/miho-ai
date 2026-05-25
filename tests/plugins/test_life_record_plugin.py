"""Tests for the thread-scoped life record PDF tools."""

from __future__ import annotations

import json
from types import SimpleNamespace

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from miho_cli.plugins import PluginContext, PluginManager, PluginManifest


def _event(thread_id: str) -> MessageEvent:
    return MessageEvent(
        text="생기부 PDF 정리해줘",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-1",
            chat_id=thread_id,
            parent_chat_id="channel-1",
            guild_id="guild-1",
            chat_name=f"thread-{thread_id}",
        ),
    )


def _fake_pdf_result() -> SimpleNamespace:
    page_texts = [
        "\n".join(
            [
                "인적·학적사항",
                "1",
                "210",
                "0",
                "0",
                "0",
                "1",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "0",
                "성명",
                "김민준",
                "백양고등학교",
                "230101-*******",
            ]
        ),
        "\n".join(
            [
                "교과학습발달상황",
                "[1학년]",
                "1",
                "국어",
                "국어",
                "4",
                "92/75.4(12.1)",
                "(210)",
                "2",
                "국어: 토론 활동에서 근거를 들어 자기 생각을 설명함. 글의 구조를 파악하고 요약하는 힘이 돋보임.",
            ]
        ),
        "행동특성 및 종합의견\n성실하게 수업에 참여하고 친구와 협력하는 태도가 안정적임.",
        "위 사람의 학교생활기록부 사본임을 증명합니다.\n성명\n김민준\n발급번호: ABC-123\n문서확인번호: 111-222\n2026년 5월 26일",
    ]
    raw_text = "\n\n".join(f"--- PAGE {i + 1} ---\n{text}" for i, text in enumerate(page_texts))
    return SimpleNamespace(
        page_texts=page_texts,
        raw_text=raw_text,
        page_count=len(page_texts),
        metadata={"format": "test"},
        photo=SimpleNamespace(
            image_bytes=b"fake-image",
            ext="png",
            source_page=1,
            width=320,
            height=420,
            sha256="photo-sha",
        ),
    )


def _payload(raw: str) -> dict:
    return json.loads(raw)


def test_life_record_tools_register() -> None:
    from plugins.life_record import register

    manager = PluginManager()
    manifest = PluginManifest(name="life_record", source="bundled", key="life_record")
    ctx = PluginContext(manifest, manager)

    register(ctx)

    assert "life_record" in manager._plugin_commands
    assert "life_record_ingest_pdf" in manager._plugin_tool_names
    assert "life_record_search" in manager._plugin_tool_names
    assert "life_record_delete" in manager._plugin_tool_names


def test_ingest_creates_thread_scoped_db_with_photo_and_three_checks(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context
    import plugins.life_record.service as service_module
    from plugins.life_record.tools import _ingest_pdf_tool_handler

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr(service_module, "extract_pdf", lambda _path: _fake_pdf_result())
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    _capture_gateway_context(_event("thread-a"))

    result = _payload(_ingest_pdf_tool_handler({"pdf_path": str(pdf_path)}))

    assert result["ok"] is True
    assert result["privacy"]["long_term_memory"] == "disabled"
    assert result["verification"]["round_count"] >= 3
    assert result["verification"]["human_review_required"] is True
    assert result["counts"]["sections"] >= 3
    assert result["counts"]["photos"] == 1
    assert "/threads/thread-thread-a__thread-a/life_records/" in result["db_path"]
    assert (tmp_path / "discord").exists()
    assert result["stored_pdf_path"].endswith("_original.pdf")
    assert result["photo_paths"][0].endswith(".png")


def test_search_does_not_cross_thread_database(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context
    import plugins.life_record.service as service_module
    from plugins.life_record.tools import _ingest_pdf_tool_handler, _search_tool_handler

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr(service_module, "extract_pdf", lambda _path: _fake_pdf_result())
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    _capture_gateway_context(_event("thread-a"))
    _ingest_pdf_tool_handler({"pdf_path": str(pdf_path)})

    _capture_gateway_context(_event("thread-b"))
    empty = _payload(_search_tool_handler({"query": "국어"}))

    assert empty["ok"] is False
    assert "현재 스레드" in empty["message"]


def test_delete_requires_confirmation_and_removes_bundle(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context
    import plugins.life_record.service as service_module
    from plugins.life_record.tools import _delete_tool_handler, _ingest_pdf_tool_handler

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr(service_module, "extract_pdf", lambda _path: _fake_pdf_result())
    pdf_path = tmp_path / "source.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    _capture_gateway_context(_event("thread-a"))
    result = _payload(_ingest_pdf_tool_handler({"pdf_path": str(pdf_path)}))

    blocked = _payload(_delete_tool_handler({"confirm_delete": False}))
    deleted = _payload(_delete_tool_handler({"confirm_delete": True}))

    assert blocked["ok"] is False
    assert "확인" in blocked["message"]
    assert deleted["ok"] is True
    assert not (tmp_path / "discord" / "guilds").joinpath(
        "guild-1", "channels", "channel-1__channel-1", "threads", "thread-thread-a__thread-a", "life_records"
    ).exists()
    assert result["db_path"].endswith("life_records.sqlite3")


def test_attendance_parser_does_not_swallow_next_section_heading() -> None:
    from plugins.life_record.parsers import parse_attendance

    text = "\n".join(
        [
            "출결상황",
            "1",
            "191",
            ".",
            ".",
            ".",
            "1",
            ".",
            ".",
            ".",
            ".",
            ".",
            ".",
            ".",
            ".",
            "원격수업일수 0일",
            "2",
            "190",
            ".",
            ".",
            ".",
            "1",
            ".",
            ".",
            "1",
            ".",
            ".",
            ".",
            ".",
            ".",
            "3",
            "190",
            "1",
            ".",
            ".",
            ".",
            ".",
            ".",
            ".",
            "9",
            ".",
            ".",
            ".",
            ".",
            "국가직무능력표준 이수상황",
        ]
    )

    rows = parse_attendance(text)

    assert [row["grade"] for row in rows] == [1, 2, 3]
    assert rows[0]["special_note"] == "원격수업일수 0일"
    assert rows[1]["special_note"] == ""
    assert rows[2]["special_note"] == ""


def test_subject_note_parser_drops_wrapped_footer_and_next_table_header() -> None:
    from plugins.life_record.parsers import parse_subject_special_notes

    text = "\n".join(
        [
            "교과학습발달상황",
            "과목 세부능력및특기사항",
            "심리학: 범죄심리학 관련 도서를 읽고 주제를 정해 탐구 보고서를 작성함.",
            "토론에서 근거를 들어 의견을 설명하고 발표함.",
            "반",
            "4",
            "번호",
            "1",
            "이름",
            "김민준",
            "백양고등학교",
            "8/28",
            "2026년 5월 21일",
            "또한 문서하단의 바코드로도 진위확인할 수 있습니다.",
            "<진로 선택 과목>",
            "원점수/과목평균 (수강자수) 성취도별 분포비율",
            "체육 체육 A",
        ]
    )

    notes = parse_subject_special_notes([text])

    assert len(notes) == 1
    assert notes[0]["subject"] == "심리학"
    assert "발표함" in notes[0]["note_text"]
    assert "김민준" not in notes[0]["note_text"]
    assert "바코드" not in notes[0]["note_text"]
    assert "<진로 선택 과목>" not in notes[0]["note_text"]
    assert "체육 체육 A" not in notes[0]["note_text"]
