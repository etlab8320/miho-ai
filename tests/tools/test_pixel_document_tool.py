"""Tests for the Pixel Document Evidence core tool."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


def _load_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants

    importlib.reload(miho_constants)
    import tools.pixel_document_tool as tool

    importlib.reload(tool)
    return tool


def _json(raw: str) -> dict:
    return json.loads(raw)


def test_pixel_document_tool_status_reports_capabilities(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(tool.pixel_document_evidence_tool({"action": "status"}))

    assert result["success"] is True
    assert result["capabilities"]["image_render"] is True
    assert "apple_vision_ocr" in result["capabilities"]


def test_pixel_document_tool_ingest_and_search_html(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)
    source = tmp_path / "guide.html"
    source.write_text("<html><body>실기 배점표 실기 70 학생부 30</body></html>", encoding="utf-8")

    ingest = _json(tool.pixel_document_evidence_tool({"action": "ingest", "source": str(source), "ocr_backend": "none"}))
    search = _json(
        tool.pixel_document_evidence_tool(
            {"action": "search", "document_id": ingest["document_id"], "query": "실기 70"}
        )
    )

    assert ingest["success"] is True
    assert ingest["ingest_status"] == "ready"
    assert search["success"] is True
    assert search["results"][0]["page_image_path"]


def test_pixel_document_tool_returns_korean_error_without_traceback(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(tool.pixel_document_evidence_tool({"action": "ingest"}))

    assert result["success"] is False
    assert "문서 경로" in result["message_ko"]
    assert "Traceback" not in json.dumps(result, ensure_ascii=False)


def test_pixel_document_tool_rejects_out_of_range_page_range_in_korean(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)
    source = tmp_path / "guide.html"
    source.write_text("<html><body>실기 배점표</body></html>", encoding="utf-8")

    result = _json(
        tool.pixel_document_evidence_tool(
            {"action": "ingest", "source": str(source), "ocr_backend": "none", "page_range": "2"}
        )
    )

    assert result["success"] is False
    assert "페이지" in result["message_ko"]
    assert "Traceback" not in json.dumps(result, ensure_ascii=False)


def test_pixel_document_tool_rejects_oversized_page_token_in_korean(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)
    source = tmp_path / "guide.html"
    source.write_text("<html><body>실기 배점표</body></html>", encoding="utf-8")

    result = _json(
        tool.pixel_document_evidence_tool(
            {"action": "ingest", "source": str(source), "ocr_backend": "none", "page_range": "9" * 5000}
        )
    )

    assert result["success"] is False
    assert "페이지 번호" in result["message_ko"]
    assert "Exceeds" not in json.dumps(result, ensure_ascii=False)
    assert "Traceback" not in json.dumps(result, ensure_ascii=False)


def test_pixel_document_tool_is_available_to_core_miho_toolsets(tmp_path, monkeypatch) -> None:
    _load_tool(tmp_path, monkeypatch)

    from toolsets import resolve_toolset

    assert "pixel_document_evidence" in resolve_toolset("miho-cli")
    assert "pixel_document_evidence" in resolve_toolset("miho-discord")


def test_pixel_document_cli_delegates_to_same_service(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    source = tmp_path / "guide.html"
    source.write_text("<html><body>학생부 30 실기 70</body></html>", encoding="utf-8")

    import scripts.pixel_document_evidence as cli

    exit_code = cli.main(["ingest", str(source), "--ocr-backend", "none", "--page-range", "1"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["ok"] is True
    assert payload["render"]["page_range"] == "1"
    assert Path(payload["manifest_path"]).exists()


def test_pixel_document_cli_returns_korean_json_error_for_invalid_page_range(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    source = tmp_path / "guide.html"
    source.write_text("<html><body>학생부 30 실기 70</body></html>", encoding="utf-8")

    import scripts.pixel_document_evidence as cli

    exit_code = cli.main(["ingest", str(source), "--ocr-backend", "none", "--page-range", "2"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["ok"] is False
    assert "페이지" in payload["message_ko"]
    assert "Traceback" not in captured.out


def test_pixel_document_cli_returns_korean_json_error_for_oversized_page_token(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    source = tmp_path / "guide.html"
    source.write_text("<html><body>학생부 30 실기 70</body></html>", encoding="utf-8")

    import scripts.pixel_document_evidence as cli

    exit_code = cli.main(["ingest", str(source), "--ocr-backend", "none", "--page-range", "9" * 5000])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 1
    assert payload["ok"] is False
    assert "페이지 번호" in payload["message_ko"]
    assert "Exceeds" not in captured.out
    assert "Traceback" not in captured.out
