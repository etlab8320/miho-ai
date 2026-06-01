"""Tests for the vision-based thread-scoped life record tools.

Vision extraction is injected (fake resolver) so unit tests never hit codex; the
opt-in live test (MIHO_LIFE_RECORD_LIVE_TEST=1) exercises the real model.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from miho_cli.plugins import PluginContext, PluginManager, PluginManifest
from plugins.life_record.context import capture_gateway_context


# ----------------------------------------------------------------- fixtures/helpers

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


SAMPLE_1 = {
    "identity": {"name": "홍길동", "school_name": "서울고등학교", "birth6": "070101", "class_no": "3", "student_no": "5"},
    "attendance": [{"grade": 1, "school_days": 190, "absence": "0", "late": "0", "early_leave": "0", "special_note": ""}],
    "grades": [{"grade": 1, "semester": 1, "category": "국어", "subject": "국어", "credits": 4, "raw_score": "90/70(10)", "achievement": "A", "students_count": 200, "rank_grade": "2"}],
    "notes": [{"grade": 1, "semester": 1, "subject": "국어", "note_text": "토론 활동에서 근거를 들어 설명함."}],
    "awards": [{"grade": 1, "title": "교과우수상(국어)", "awarded_at": "2024-07-19", "issuer": "서울고등학교장"}],
}


def _fake_resolver_factory(payload):
    async def _resolver(images, prompt):
        return json.dumps(payload, ensure_ascii=False)
    return _resolver


def _patch_vision(monkeypatch, payload, *, pages=1):
    import plugins.life_record.service as service_module
    import plugins.life_record.vision_extractor as vision_module
    monkeypatch.setattr(service_module, "render_page_images", lambda *a, **k: [b"\x89PNG\r\n\x1a\n"] * pages)
    monkeypatch.setattr(service_module, "_safe_photo", lambda _p: None)
    monkeypatch.setattr(vision_module, "default_codex_resolver", _fake_resolver_factory(payload))


def _ingest(monkeypatch, tmp_path, thread_id, payload, pdf_name="source.pdf"):
    from plugins.life_record import _capture_gateway_context
    from plugins.life_record.tools import _ingest_pdf_tool_handler
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    _patch_vision(monkeypatch, payload)
    pdf_path = tmp_path / pdf_name
    pdf_path.write_bytes(b"%PDF-1.4 fake")
    capture_gateway_context(_event(thread_id))
    return json.loads(_ingest_pdf_tool_handler({"pdf_path": str(pdf_path)}))


# ----------------------------------------------------------------- T-10 register

def test_life_record_tools_register() -> None:
    from plugins.life_record import register
    manager = PluginManager()
    register(PluginContext(PluginManifest(name="life_record", source="bundled", key="life_record"), manager))
    for tool in ("life_record_ingest_pdf", "life_record_verify", "life_record_search", "life_record_summary", "life_record_delete", "life_record_lookup", "life_record_confirm"):
        assert tool in manager._plugin_tool_names


# ----------------------------------------------------------------- T-01 render

def test_render_page_images_produces_png_bytes(tmp_path) -> None:
    fitz = pytest.importorskip("fitz")
    from plugins.life_record.pdf_reader import render_page_images
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    pdf = tmp_path / "two.pdf"
    doc.save(str(pdf))
    doc.close()
    images = render_page_images(pdf, zoom=2.0)
    assert len(images) == 2
    assert images[0][:8] == b"\x89PNG\r\n\x1a\n"


# ----------------------------------------------------------------- T-02 vision parse

def test_vision_extractor_normalizes_and_masks() -> None:
    from plugins.life_record.vision_extractor import parse_extraction_json
    raw = "```json\n" + json.dumps({"identity": {"name": "김철수", "birth6": "070101-3xxxxxx"}, "grades": [{"subject": "수학"}]}) + "\n```"
    parsed = parse_extraction_json(raw)
    assert parsed["identity"]["name"] == "김철수"
    assert parsed["identity"]["birth6"] == "070101"  # back digits stripped (T-09)
    assert parsed["grades"][0]["subject"] == "수학"


# ----------------------------------------------------------------- T-03/T-04 consensus

def test_consensus_majority_confirms() -> None:
    from plugins.life_record.consensus import reconcile, all_confirmed
    r = reconcile([SAMPLE_1, SAMPLE_1, dict(SAMPLE_1, identity=dict(SAMPLE_1["identity"], name="홍길순"))])
    assert r["identity"]["name"]["value"] == "홍길동"
    assert r["identity"]["name"]["agreed"] is True
    assert r["grades"][0]["_status"] == "confirmed"


def test_consensus_disagreement_needs_review_no_infinite_loop() -> None:
    from plugins.life_record.consensus import reconcile, needs_recheck_fields, all_confirmed
    a = dict(SAMPLE_1, identity={"name": "A", "school_name": "X고", "birth6": "070101", "class_no": "1", "student_no": "1"})
    b = dict(SAMPLE_1, identity={"name": "B", "school_name": "Y고", "birth6": "070202", "class_no": "2", "student_no": "2"})
    r = reconcile([a, b])  # 2 runs, all differ -> no majority
    assert r["identity"]["name"]["agreed"] is False
    assert "name" in needs_recheck_fields(r["identity"])
    assert all_confirmed(r) is False


def test_consensus_folds_roman_numeral_subject_variants() -> None:
    # vision reads the same subject as '물리학Ⅰ' (Unicode Roman) and '물리학 I'
    # (ASCII I + space) across runs — must fold to ONE confirmed row, not two.
    from plugins.life_record.consensus import reconcile_rows, CONFIRMED
    a = {"grades": [{"grade": 2, "semester": 1, "subject": "물리학Ⅰ", "raw_score": "79/70.8(18.3)"}]}
    b = {"grades": [{"grade": 2, "semester": 1, "subject": "물리학 I", "raw_score": "79/70.8(18.3)"}]}
    rows = reconcile_rows([a, b], "grades")
    assert len(rows) == 1
    assert rows[0]["_status"] == CONFIRMED


# ----------------------------------------------------------------- T-06 identity / T-07 promote / ingest flow

def test_ingest_creates_thread_db_and_confirms_on_consensus(monkeypatch, tmp_path) -> None:
    # T-07: full consensus → promote_to_central (result["promoted"]["ok"])
    result = _ingest(monkeypatch, tmp_path, "thread-a", SAMPLE_1)
    assert result["ok"] is True
    assert result["privacy"]["long_term_memory"] == "disabled"
    assert result["student"]["name"] == "홍길동"
    assert result["consensus_complete"] is True  # identical runs -> all confirmed
    assert result["promoted"] and result["promoted"]["ok"] is True
    assert result["counts"]["subject_grade_rows"] == 1
    assert "/threads/thread-thread-a__thread-a/life_records/" in result["db_path"]


def test_same_student_reingest_keeps_single_student(monkeypatch, tmp_path) -> None:
    from plugins.life_record.repository import connect_central, central_db_path
    _ingest(monkeypatch, tmp_path, "thread-a", SAMPLE_1, pdf_name="g1.pdf")
    # Grade 2·3 semesters for the SAME student (same name+school+birth)
    grades_23 = dict(SAMPLE_1, grades=[
        {"grade": 2, "semester": 1, "category": "수학", "subject": "수학", "credits": 4, "raw_score": "88/70(9)", "achievement": "B", "students_count": 200, "rank_grade": "3"},
        {"grade": 3, "semester": 1, "category": "영어", "subject": "영어", "credits": 4, "raw_score": "95/72(8)", "achievement": "A", "students_count": 200, "rank_grade": "1"},
    ])
    _ingest(monkeypatch, tmp_path, "thread-b", grades_23, pdf_name="g23.pdf")
    conn = connect_central(central_db_path())
    try:
        students = conn.execute("SELECT * FROM students").fetchall()
        grades = conn.execute("SELECT grade, subject FROM central_grades ORDER BY grade").fetchall()
    finally:
        conn.close()
    assert len(students) == 1  # T-06: one student, not duplicated
    assert {(g["grade"], g["subject"]) for g in grades} == {(1, "국어"), (2, "수학"), (3, "영어")}  # T-05: accumulated


# ----------------------------------------------------------------- T-08 lookup

def test_lookup_central_returns_accumulated_student(monkeypatch, tmp_path) -> None:
    from plugins.life_record.tools import _lookup_tool_handler
    _ingest(monkeypatch, tmp_path, "thread-a", SAMPLE_1)
    result = json.loads(_lookup_tool_handler({"query": "홍길동"}))
    assert result["ok"] is True
    assert result["total"] == 1
    student = result["students"][0]
    assert student["name"] == "홍길동"
    assert any(g["subject"] == "국어" for g in student["grades"])


# ----------------------------------------------------------------- T-11 confirm

def test_confirm_promotes_needs_review_rows(monkeypatch, tmp_path) -> None:
    from plugins.life_record.tools import _confirm_tool_handler
    # Two differing runs -> grades stay needs_review, not auto-promoted
    payload_b = dict(SAMPLE_1, grades=[dict(SAMPLE_1["grades"][0], raw_score="91/70(10)")])
    payload_c = dict(SAMPLE_1, grades=[dict(SAMPLE_1["grades"][0], raw_score="92/70(10)")])
    import plugins.life_record.service as service_module
    import plugins.life_record.vision_extractor as vision_module
    from plugins.life_record import _capture_gateway_context
    from plugins.life_record.tools import _ingest_pdf_tool_handler
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    monkeypatch.setattr(service_module, "render_page_images", lambda *a, **k: [b"\x89PNG\r\n\x1a\n"])
    monkeypatch.setattr(service_module, "_safe_photo", lambda _p: None)
    # 3 runs all differ on raw_score → no majority → stays needs_review
    seq = [SAMPLE_1, payload_b, payload_c]
    calls = {"i": 0}
    async def _vary(images, prompt):
        payload = seq[min(calls["i"], len(seq) - 1)]
        calls["i"] += 1
        return json.dumps(payload, ensure_ascii=False)
    monkeypatch.setattr(vision_module, "default_codex_resolver", _vary)
    pdf = tmp_path / "v.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    capture_gateway_context(_event("thread-a"))
    ingest = json.loads(_ingest_pdf_tool_handler({"pdf_path": str(pdf)}))
    # disagreement on raw_score -> not fully confirmed
    assert ingest["counts"]["needs_review_rows"] >= 1
    confirmed = json.loads(_confirm_tool_handler({"confirm": True}))
    assert confirmed["ok"] is True
    assert confirmed["confirmed_rows"] >= 1
    assert confirmed["promoted"]["ok"] is True


def test_confirm_requires_flag(monkeypatch, tmp_path) -> None:
    from plugins.life_record.tools import _confirm_tool_handler
    _ingest(monkeypatch, tmp_path, "thread-a", SAMPLE_1)
    blocked = json.loads(_confirm_tool_handler({"confirm": False}))
    assert blocked["ok"] is False


# ----------------------------------------------------------------- search / delete (thread isolation)

def test_search_is_thread_scoped(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context
    from plugins.life_record.tools import _search_tool_handler
    _ingest(monkeypatch, tmp_path, "thread-a", SAMPLE_1)
    capture_gateway_context(_event("thread-b"))
    other = json.loads(_search_tool_handler({"query": "국어"}))
    assert other["count"] == 0  # thread-b has no data


def test_delete_requires_confirmation(monkeypatch, tmp_path) -> None:
    from plugins.life_record.tools import _delete_tool_handler
    _ingest(monkeypatch, tmp_path, "thread-a", SAMPLE_1)
    blocked = json.loads(_delete_tool_handler({"confirm_delete": False}))
    deleted = json.loads(_delete_tool_handler({"confirm_delete": True}))
    assert blocked["ok"] is False
    assert deleted["ok"] is True


# ----------------------------------------------------------------- T-13/T-14 PDF auto-route

def test_attached_pdf_auto_routes_to_ingest_without_tool_name(monkeypatch, tmp_path) -> None:
    # User attaches a 생기부 PDF with no tool name — gateway must auto-ingest.
    from plugins.life_record import _capture_gateway_context
    import plugins.life_record.service as service_module
    import plugins.life_record.vision_extractor as vision_module
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    pdf = tmp_path / "attached.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(service_module, "render_page_images", lambda *a, **k: [b"\x89PNG\r\n\x1a\n"])
    monkeypatch.setattr(service_module, "_safe_photo", lambda _p: None)

    async def _smart(images, prompt):
        # the 1-page gate asks a yes/no question; extraction asks for JSON
        if "한 단어" in prompt:
            return "yes"
        return json.dumps(SAMPLE_1, ensure_ascii=False)

    monkeypatch.setattr(vision_module, "default_codex_resolver", _smart)
    event = _event("thread-a")
    event.media_urls = [str(pdf)]
    result = asyncio.run(_capture_gateway_context(event))
    assert result["action"] == "respond"
    assert "생기부" in result["text"]
    assert "홍길동" in result["text"]


def test_non_life_record_pdf_passes_through(monkeypatch, tmp_path) -> None:
    # A PDF the gate says 'no' to must NOT be ingested — pass to body agent.
    from plugins.life_record import _capture_gateway_context
    import plugins.life_record.service as service_module
    import plugins.life_record.vision_extractor as vision_module
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(service_module, "render_page_images", lambda *a, **k: [b"\x89PNG\r\n\x1a\n"])

    async def _no(images, prompt):
        return "no"

    monkeypatch.setattr(vision_module, "default_codex_resolver", _no)
    event = _event("thread-a")
    event.media_urls = [str(pdf)]
    result = asyncio.run(_capture_gateway_context(event))
    assert result["action"] == "allow"


def test_no_attachment_passes_through(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    event = _event("thread-a")
    result = asyncio.run(_capture_gateway_context(event))
    assert result["action"] == "allow"


# ----------------------------------------------------------------- T-12 live (opt-in)

@pytest.mark.skipif(os.environ.get("MIHO_LIFE_RECORD_LIVE_TEST") != "1", reason="opt-in live vision test")
def test_live_vision_extraction_on_real_samples(tmp_path, monkeypatch) -> None:
    from plugins.life_record import _capture_gateway_context
    from plugins.life_record.tools import _ingest_pdf_tool_handler
    samples = [Path("/Users/etlab/Downloads/김동혁생기부.pdf"), Path("/Users/etlab/Downloads/120260521102310194.pdf")]
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    for i, pdf in enumerate(samples):
        if not pdf.exists():
            pytest.skip(f"sample missing: {pdf}")
        capture_gateway_context(_event(f"live-{i}"))
        result = json.loads(_ingest_pdf_tool_handler({"pdf_path": str(pdf)}))
        assert result["ok"] is True
        assert result["student"]["name"]  # vision read a name
        assert result["counts"]["subject_grade_rows"] >= 0
