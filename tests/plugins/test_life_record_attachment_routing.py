"""Attachment routing tests for life-record document format sniffing."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource

SAMPLE_RECORD = {
    "identity": {"name": "홍길동", "school_name": "서울고등학교", "birth6": "070101", "class_no": "3", "student_no": "5"},
    "attendance": [{"grade": 1, "school_days": 190, "absence": "0", "late": "0", "early_leave": "0", "special_note": ""}],
    "grades": [{"grade": 1, "semester": 1, "category": "국어", "subject": "국어", "credits": 4, "raw_score": "90/70(10)", "achievement": "A", "students_count": 200, "rank_grade": "2"}],
    "notes": [{"grade": 1, "semester": 1, "subject": "국어", "note_text": "근거를 들어 설명함."}],
    "awards": [],
}


def _event(thread_id: str) -> MessageEvent:
    return MessageEvent(
        text="백종환 생기부자료 다 넣어줘",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-1",
            chat_id=thread_id,
            parent_chat_id="channel-1",
            guild_id="guild-1",
            chat_name=f"thread-{thread_id}",
        ),
    )


def _authed_gateway() -> SimpleNamespace:
    return SimpleNamespace(_is_user_authorized=lambda _source: True, session_store=None)


def _write_mhtml(path: Path) -> None:
    source_text = "학교생활기록부 교과학습발달상황 출결상황 " * 40
    path.write_text(
        "MIME-Version: 1.0\nContent-Type: text/html; charset=utf-8\n\n"
        f"<html><body>{source_text}</body></html>",
        encoding="utf-8",
    )


def _patch_text_mhtml(monkeypatch, tmp_path) -> None:
    import plugins.life_record.service as service_module
    import plugins.life_record.vision_extractor as vision_module

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    def _fake_text_pdf(page_texts, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-1.4 source text")
        return output_path

    async def _text_fake(prompt):
        assert "학교생활기록부" in prompt
        return json.dumps(SAMPLE_RECORD, ensure_ascii=False)

    async def _vision_must_not_run(images, prompt):
        raise AssertionError("text-rich MHTML must not call the vision resolver")

    monkeypatch.setattr(service_module, "create_text_pdf", _fake_text_pdf)
    monkeypatch.setattr(service_module, "extract_pdf", lambda _p: SimpleNamespace(page_texts=[], raw_text="", page_count=1, metadata={}, photo=None))
    monkeypatch.setattr(service_module, "render_page_images", lambda *a, **k: [b"\x89PNG\r\n\x1a\n"])
    monkeypatch.setattr(vision_module, "default_text_resolver", _text_fake)
    monkeypatch.setattr(vision_module, "default_codex_resolver", _vision_must_not_run)


def test_extract_mhtml_text_decodes_html_source(tmp_path) -> None:
    from plugins.life_record.pdf_reader import extract_mhtml_text

    mhtml = tmp_path / "record.mhtml"
    mhtml.write_text(
        "MIME-Version: 1.0\nContent-Type: text/html; charset=utf-8\n\n"
        "<html><body><h1>학교생활기록부</h1><table><tr><td>교과학습발달상황</td></tr></table></body></html>",
        encoding="utf-8",
    )

    text = "\n".join(extract_mhtml_text(mhtml))

    assert "학교생활기록부" in text
    assert "교과학습발달상황" in text
    assert "<table>" not in text


def test_discord_cached_mhtml_txt_auto_routes_by_content(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context

    _patch_text_mhtml(monkeypatch, tmp_path)
    cached = tmp_path / "doc_330496b63d85_mhtml.txt"
    _write_mhtml(cached)

    event = _event("thread-mhtml-txt")
    event.media_urls = [str(cached)]
    result = asyncio.run(_capture_gateway_context(event, gateway=_authed_gateway()))

    assert result["action"] == "respond"
    assert "홍길동" in result["text"]


def test_unknown_suffix_mhtml_auto_routes_by_content(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context

    _patch_text_mhtml(monkeypatch, tmp_path)
    cached = tmp_path / "uploaded-cache-file.bin"
    _write_mhtml(cached)

    event = _event("thread-mhtml-bin")
    event.media_urls = [str(cached)]
    result = asyncio.run(_capture_gateway_context(event, gateway=_authed_gateway()))

    assert result["action"] == "respond"
    assert "홍길동" in result["text"]


def test_mhtml_ingest_preserves_original_and_stores_converted_pdf(monkeypatch, tmp_path) -> None:
    from plugins.life_record.context import capture_gateway_context
    from plugins.life_record.tools import _ingest_pdf_tool_handler
    import plugins.life_record.service as service_module
    import plugins.life_record.vision_extractor as vision_module

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    mhtml = tmp_path / "record.mht"
    mhtml.write_text("MIME-Version: 1.0\n\n학교생활기록부", encoding="utf-8")

    def _fake_convert(src, out_dir):
        out = out_dir / f"{src.stem}_from_mhtml.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"%PDF-1.4 converted")
        return out

    async def _vision_fake(_images, _prompt):
        return json.dumps(SAMPLE_RECORD, ensure_ascii=False)

    monkeypatch.setattr(service_module, "convert_mhtml_to_pdf", _fake_convert)
    monkeypatch.setattr(service_module, "extract_pdf", lambda _p: SimpleNamespace(page_texts=[], raw_text="", page_count=1, metadata={}, photo=None))
    monkeypatch.setattr(service_module, "render_page_images", lambda *a, **k: [b"\x89PNG\r\n\x1a\n"])
    monkeypatch.setattr(vision_module, "default_codex_resolver", _vision_fake)

    capture_gateway_context(_event("thread-mhtml-save"))
    result = json.loads(_ingest_pdf_tool_handler({"pdf_path": str(mhtml)}))

    assert result["ok"] is True
    assert result["student"]["name"] == "홍길동"
    assert result["stored_original_path"].endswith("_original.mht")
    assert Path(result["stored_original_path"]).exists()
    assert result["stored_pdf_path"].endswith("_original.pdf")
    assert Path(result["stored_pdf_path"]).exists()


def test_plain_txt_attachment_does_not_become_life_record_candidate(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context
    import plugins.life_record.service as service_module

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    called = {"gate": False}

    async def _gate_must_not_run(*_args, **_kwargs):
        called["gate"] = True
        return True

    plain = tmp_path / "memo.txt"
    plain.write_text("오늘 상담 메모와 할 일 목록입니다.", encoding="utf-8")
    monkeypatch.setattr(service_module, "looks_like_life_record", _gate_must_not_run)

    event = _event("thread-plain-txt")
    event.media_urls = [str(plain)]
    result = asyncio.run(_capture_gateway_context(event, gateway=_authed_gateway()))

    assert result["action"] == "allow"
    assert called["gate"] is False


def test_non_life_record_mhtml_text_passes_without_vision(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context
    import plugins.life_record.service as service_module
    import plugins.life_record.vision_extractor as vision_module

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    rendered = {"count": 0}

    def _render_must_not_run(*_args, **_kwargs):
        rendered["count"] += 1
        raise AssertionError("non-life-record MHTML text should pass before vision")

    async def _vision_must_not_run(*_args, **_kwargs):
        raise AssertionError("non-life-record MHTML text should not ask vision")

    mhtml = tmp_path / "invoice.mhtml.txt"
    mhtml.write_text(
        "MIME-Version: 1.0\nContent-Type: text/html; charset=utf-8\n\n"
        "<html><body><h1>거래명세서</h1><p>일반 청구 문서입니다.</p></body></html>",
        encoding="utf-8",
    )
    monkeypatch.setattr(service_module, "render_page_images", _render_must_not_run)
    monkeypatch.setattr(vision_module, "default_codex_resolver", _vision_must_not_run)

    event = _event("thread-non-life-mhtml")
    event.media_urls = [str(mhtml)]
    result = asyncio.run(_capture_gateway_context(event, gateway=_authed_gateway()))

    assert result["action"] == "allow"
    assert rendered["count"] == 0
