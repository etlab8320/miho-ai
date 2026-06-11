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


def _write_neis_mhtml(path: Path) -> None:
    note = "수업에 성실히 참여하고 근거를 들어 설명함. " * 12
    path.write_text(
        "MIME-Version: 1.0\nContent-Type: text/plain; charset=utf-8\nContent-Location: https://www.neisplus.kr/csp-std/\n\n"
        "학교생활기록부\n\n"
        "학반정보\n학년\n학과\n반\n번호\n담임성명\n1\n7\n8\n김교사\n"
        "1. 인적·학적사항\n성명\n홍길동\n주민등록번호\n070101-*******\n학적사항\n"
        "2024년 03월 01일 서울고등학교 제1학년 입학\n"
        "2. 출결상황\n학년\n수업일수\n결석일수\n지 각\n조 퇴\n결 과\n특기사항\n"
        "1\n190\n0\n.\n.\n1\n.\n.\n0\n.\n.\n.\n.\n.\n"
        "3. 수상경력\n"
        "6. 창의적 체험활동상황\n학년\n영역\n시간\n특기사항\n1\n자율활동\n10\n"
        f"{note}\n"
        "7. 교과학습발달상황\n1학년\n학기\n교과\n과목\n학점수\n원점수/과목평균(표준편차)\n성취도(수강자수)\n석차등급\n"
        "1\n국어\n국어\n4\n90/70.0(10.0)\nA(200)\n2\n"
        "세부능력 및 특기사항\n국어: 발표와 토론에서 논리적으로 의견을 제시함.\n"
        "9. 행동특성 및 종합의견\n학년\n행동특성 및 종합의견\n1\n책임감 있게 학급 활동에 참여함.\n개인정보처리방침\n",
        encoding="utf-8",
    )


def _patch_mhtml_ingest_io(monkeypatch, tmp_path) -> None:
    import plugins.life_record.service as service_module
    import plugins.life_record.vision_extractor as vision_module

    monkeypatch.setenv("MIHO_HOME", str(tmp_path))

    def _fake_text_pdf(page_texts, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-1.4 source text")
        return output_path

    async def _vision_must_not_run(images, prompt):
        raise AssertionError("text-rich MHTML must not call the vision resolver")

    monkeypatch.setattr(service_module, "create_text_pdf", _fake_text_pdf)
    monkeypatch.setattr(service_module, "extract_pdf", lambda _p: SimpleNamespace(page_texts=[], raw_text="", page_count=1, metadata={}, photo=None))
    monkeypatch.setattr(service_module, "render_page_images", lambda *a, **k: [b"\x89PNG\r\n\x1a\n"])
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


def test_mhtml_source_parser_keeps_no_rank_grade_rows(tmp_path) -> None:
    from plugins.life_record.mhtml_source import extract_from_mhtml_source
    from plugins.life_record.pdf_reader import extract_mhtml_text

    mhtml = tmp_path / "record.mhtml.txt"
    _write_neis_mhtml(mhtml)
    source = mhtml.read_text(encoding="utf-8")
    source = source.replace(
        "세부능력 및 특기사항",
        "2\n과학\n과학탐구실험\n1\n58/76.8(16.6)\nC(251)\n세부능력 및 특기사항",
    )
    mhtml.write_text(source, encoding="utf-8")

    parsed = extract_from_mhtml_source(extract_mhtml_text(mhtml))
    subjects = [(row["semester"], row["subject"], row["rank_grade"]) for row in parsed["grades"]]

    assert (2, "과학탐구실험", None) in subjects
    assert len(parsed["grades"]) == 2


def test_discord_cached_mhtml_txt_auto_routes_by_content(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context

    _patch_text_mhtml(monkeypatch, tmp_path)
    cached = tmp_path / "doc_330496b63d85_mhtml.txt"
    _write_mhtml(cached)

    event = _event("thread-mhtml-txt")
    event.media_urls = [str(cached)]
    result = asyncio.run(_capture_gateway_context(event, gateway=_authed_gateway()))

    assert result["action"] == "respond"
    assert "생기부 원본" in result["text"]


def test_unknown_suffix_mhtml_auto_routes_by_content(monkeypatch, tmp_path) -> None:
    from plugins.life_record import _capture_gateway_context

    _patch_text_mhtml(monkeypatch, tmp_path)
    cached = tmp_path / "uploaded-cache-file.bin"
    _write_mhtml(cached)

    event = _event("thread-mhtml-bin")
    event.media_urls = [str(cached)]
    result = asyncio.run(_capture_gateway_context(event, gateway=_authed_gateway()))

    assert result["action"] == "respond"
    assert "생기부 원본" in result["text"]


def test_mhtml_ingest_preserves_original_as_primary_document(monkeypatch, tmp_path) -> None:
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
    assert result["stored_pdf_path"].endswith("_original.mht")
    assert Path(result["stored_pdf_path"]).exists()
    assert result["converted_pdf_path"].endswith("_from_mhtml.pdf")


def test_text_rich_mhtml_timeout_stores_review_without_retries(monkeypatch, tmp_path) -> None:
    from plugins.life_record.context import capture_gateway_context
    from plugins.life_record.tools import _ingest_pdf_tool_handler
    import plugins.life_record.vision_extractor as vision_module

    _patch_mhtml_ingest_io(monkeypatch, tmp_path)
    calls = {"text": 0}

    async def _text_timeout(prompt):
        calls["text"] += 1
        raise RuntimeError("text model timeout")

    monkeypatch.setattr(vision_module, "default_text_resolver", _text_timeout)
    mhtml = tmp_path / "record.mhtml.txt"
    _write_neis_mhtml(mhtml)

    capture_gateway_context(_event("thread-mhtml-timeout"))
    result = json.loads(_ingest_pdf_tool_handler({"pdf_path": str(mhtml)}))

    assert result["ok"] is True
    assert calls["text"] == 0
    assert result["student"]["name"] == "홍길동"
    assert result["consensus_complete"] is False
    assert result["counts"]["needs_review_rows"] > 0
    assert result["runs"] == 2


def test_text_rich_mhtml_uses_single_model_pass(monkeypatch, tmp_path) -> None:
    from plugins.life_record.context import capture_gateway_context
    from plugins.life_record.tools import _ingest_pdf_tool_handler
    import plugins.life_record.vision_extractor as vision_module

    _patch_mhtml_ingest_io(monkeypatch, tmp_path)
    calls = {"text": 0}

    async def _text_fake(prompt):
        calls["text"] += 1
        return json.dumps(SAMPLE_RECORD, ensure_ascii=False)

    monkeypatch.setenv("MIHO_LIFE_RECORD_MHTML_MODEL_PASS", "1")
    monkeypatch.setattr(vision_module, "default_text_resolver", _text_fake)
    mhtml = tmp_path / "record.mhtml.txt"
    _write_neis_mhtml(mhtml)

    capture_gateway_context(_event("thread-mhtml-single-pass"))
    result = json.loads(_ingest_pdf_tool_handler({"pdf_path": str(mhtml)}))

    assert result["ok"] is True
    assert calls["text"] == 1
    assert result["runs"] == 2


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
