"""Pixel document evidence service tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


class _Ctx:
    def __init__(self) -> None:
        self.tasks: list[dict[str, Any]] = []

    def register_auxiliary_task(self, key: str, **kwargs: Any) -> None:
        self.tasks.append({"key": key, **kwargs})


def _write_html(path: Path) -> None:
    path.write_text(
        "<html><body><h1>2027 체육교육과 모집요강</h1>"
        "<table><tr><td>실기</td><td>70%</td></tr>"
        "<tr><td>학생부</td><td>30%</td></tr></table></body></html>",
        encoding="utf-8",
    )


def _write_pdf(path: Path, page_texts: list[str]) -> None:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    try:
        for text in page_texts:
            page = doc.new_page()
            page.insert_text((72, 72), text, fontsize=18)
        doc.save(str(path))
    finally:
        doc.close()


def test_plugin_registers_reviewer_agent() -> None:
    from plugins import pixel_documents

    ctx = _Ctx()
    pixel_documents.register(ctx)

    keys = {task["key"] for task in ctx.tasks}
    assert "pixel_document_reviewer" in keys


def test_plugin_loads_as_bundled_backend(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    from miho_cli.plugins import PluginManager, get_plugin_auxiliary_tasks

    manager = PluginManager()
    manager.discover_and_load()

    loaded = manager._plugins["pixel_documents"]
    assert loaded.enabled
    assert loaded.error is None
    assert any(task["key"] == "pixel_document_reviewer" for task in get_plugin_auxiliary_tasks())


def test_html_fallback_ingest_creates_page_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    from plugins.pixel_documents.service import ingest_document

    source = tmp_path / "guide.html"
    _write_html(source)

    result = ingest_document(str(source), ocr_backend="none")

    assert result["ok"] is True
    assert result["ingest_status"] == "ready"
    assert result["document_id"]
    assert Path(result["manifest_path"]).exists()
    assert result["pages"][0]["render_mode"] == "text_fallback"
    assert result["pages"][0]["page_image_path"]
    assert "실기" in result["pages"][0]["text"]
    assert result["reviewer"]["status"] == "pass"


def test_image_without_ocr_is_provisional_not_dead_end(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    from PIL import Image
    from plugins.pixel_documents.service import ingest_document

    image = tmp_path / "scan.png"
    Image.new("RGB", (320, 180), "white").save(image)

    result = ingest_document(str(image), ocr_backend="none")

    assert result["ok"] is True
    assert result["ingest_status"] == "provisional"
    assert result["pages"][0]["text"] == ""
    assert result["ocr"]["status"] == "skipped"
    assert result["retry_tools"] == ["pixel_document_evidence"]
    assert "못" not in result["message_ko"]


def test_search_returns_page_image_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    from plugins.pixel_documents.service import ingest_document, search_document

    source = tmp_path / "guide.html"
    _write_html(source)
    ingest = ingest_document(str(source), ocr_backend="none")

    result = search_document(ingest["document_id"], "실기 70", limit=3)

    assert result["ok"] is True
    assert result["count"] == 1
    hit = result["results"][0]
    assert hit["page_number"] == 1
    assert Path(hit["page_image_path"]).exists()
    assert "실기" in hit["excerpt"]
    assert hit["reviewer"]["status"] == "pass"


def test_pdf_ingest_page_range_keeps_original_page_numbers(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    from plugins.pixel_documents.service import ingest_document, search_document

    source = tmp_path / "guide.pdf"
    _write_pdf(source, ["PAGE_ONE", "SILGI_TABLE_PAGE_TWO", "PAGE_THREE"])

    ingest = ingest_document(str(source), ocr_backend="none", page_range="2")
    search = search_document(ingest["document_id"], "SILGI_TABLE", limit=3)

    assert ingest["ok"] is True
    assert ingest["render"]["page_range"] == "2"
    assert ingest["render"]["selected_pages"] == [2]
    assert [page["page_number"] for page in ingest["pages"]] == [2]
    assert "SILGI_TABLE_PAGE_TWO" in ingest["pages"][0]["text"]
    assert search["results"][0]["page_number"] == 2


def test_pdf_page_range_uses_distinct_manifest_per_render_options(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    from plugins.pixel_documents.service import ingest_document, search_document
    from plugins.pixel_documents.storage import load_manifest

    source = tmp_path / "guide.pdf"
    _write_pdf(source, ["FULL_RANGE_ONLY", "PAGE_TWO_ONLY"])

    full = ingest_document(str(source), ocr_backend="none")
    page_two = ingest_document(str(source), ocr_backend="none", page_range="2")

    assert full["document_id"] != page_two["document_id"]
    assert [page["page_number"] for page in load_manifest(full["document_id"])["pages"]] == [1, 2]
    assert [page["page_number"] for page in load_manifest(page_two["document_id"])["pages"]] == [2]
    assert search_document(full["document_id"], "FULL_RANGE_ONLY")["count"] == 1
    assert search_document(page_two["document_id"], "FULL_RANGE_ONLY")["count"] == 0


def test_pdf_page_range_rejects_explicit_range_over_max_pages(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    from plugins.pixel_documents.service import ingest_document

    source = tmp_path / "guide.pdf"
    _write_pdf(source, ["ONE", "TWO", "THREE"])

    with pytest.raises(ValueError, match="최대 렌더 페이지 수"):
        ingest_document(str(source), ocr_backend="none", page_range="1-3", max_pages=2)


def test_page_range_rejects_huge_range_without_expanding(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    from plugins.pixel_documents.service import ingest_document

    source = tmp_path / "guide.html"
    _write_html(source)

    with pytest.raises(ValueError, match="페이지 번호"):
        ingest_document(str(source), ocr_backend="none", page_range="1-1000000000")


def test_fake_ocr_span_search_creates_crop(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    from PIL import Image
    from plugins.pixel_documents.service import ingest_document, search_document

    image = tmp_path / "scan.png"
    Image.new("RGB", (600, 400), "white").save(image)

    def fake_ocr_pages(pages: list[dict[str, Any]], *_: Any, **__: Any) -> dict[str, Any]:
        for page in pages:
            page["text"] = "실기 70 학생부 30"
            page["text_source"] = "ocr"
            page["ocr_spans"] = [
                {"text": "실기 70", "confidence": 0.99, "bbox": {"x": 0.1, "y": 0.2, "w": 0.4, "h": 0.2}}
            ]
        return {"backend": "fake", "available": True, "status": "ready", "page_count": len(pages)}

    monkeypatch.setattr("plugins.pixel_documents.service.ocr_pages", fake_ocr_pages)
    ingest = ingest_document(str(image), ocr_backend="apple_vision")
    result = search_document(ingest["document_id"], "실기", limit=1)

    hit = result["results"][0]
    assert Path(hit["crop_path"]).exists()
    assert hit["bbox"]["w"] > 0


def test_apple_vision_request_forces_pixel_ocr_on_pdf_text_layer(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    from plugins.pixel_documents.service import ingest_document

    source = tmp_path / "guide.pdf"
    _write_pdf(source, ["PDF_TEXT_LAYER_ONLY"])

    def fake_ocr_pages(pages: list[dict[str, Any]], *_: Any, **__: Any) -> dict[str, Any]:
        for page in pages:
            assert page["text"] == "PDF_TEXT_LAYER_ONLY"
            page["embedded_text"] = page["text"]
            page["text"] = "APPLE_VISION_PIXEL_OCR"
            page["text_source"] = "apple_vision_ocr"
            page["ocr_spans"] = []
        return {"backend": "fake", "available": True, "status": "ready", "page_count": len(pages)}

    monkeypatch.setattr("plugins.pixel_documents.service.ocr_pages", fake_ocr_pages)

    result = ingest_document(str(source), ocr_backend="apple_vision")

    page = result["pages"][0]
    assert page["embedded_text"] == "PDF_TEXT_LAYER_ONLY"
    assert page["text"] == "APPLE_VISION_PIXEL_OCR"
    assert page["text_source"] == "apple_vision_ocr"


def test_ocr_backend_does_not_skip_existing_text_when_apple_vision_is_requested(tmp_path, monkeypatch) -> None:
    from plugins.pixel_documents.ocr import ocr_pages

    image = tmp_path / "page.png"
    image.write_bytes(b"fake image")
    calls: list[Path] = []

    monkeypatch.setattr("plugins.pixel_documents.ocr._load_apple_vision", lambda install: ("Foundation", "Quartz", "Vision"))

    def fake_recognize(path: Path, *_: Any) -> tuple[str, list[dict[str, Any]]]:
        calls.append(path)
        return "PIXEL_TEXT", [{"text": "PIXEL_TEXT", "confidence": 0.99, "bbox": {"x": 0, "y": 0, "w": 1, "h": 1}}]

    monkeypatch.setattr("plugins.pixel_documents.ocr._recognize_text", fake_recognize)
    pages = [{"page_image_path": str(image), "text": "EMBEDDED_TEXT", "text_source": "pdf_text_layer"}]

    result = ocr_pages(pages, backend="apple_vision")

    assert result["status"] == "ready"
    assert calls == [image]
    assert pages[0]["embedded_text"] == "EMBEDDED_TEXT"
    assert pages[0]["text"] == "PIXEL_TEXT"
    assert pages[0]["text_source"] == "apple_vision_ocr"


def test_manifest_json_is_reloadable(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    from plugins.pixel_documents.service import ingest_document
    from plugins.pixel_documents.storage import load_manifest

    source = tmp_path / "guide.html"
    _write_html(source)
    result = ingest_document(str(source), ocr_backend="none")
    loaded = load_manifest(result["manifest_path"])

    assert loaded["document_id"] == result["document_id"]
    assert json.dumps(loaded, ensure_ascii=False)
