"""Tests for governed media delivery contract tool."""

from __future__ import annotations

import importlib
import json

from toolsets import resolve_toolset


def _load_tool(monkeypatch, tmp_path):
    monkeypatch.setenv("MIHO_MEDIA_ALLOW_DIRS", str(tmp_path))

    import tools.media_delivery_contract_tool as tool

    importlib.reload(tool)
    return tool


def _json(raw: str) -> dict:
    return json.loads(raw)


def test_media_delivery_contract_returns_reviewed_media_tag(tmp_path, monkeypatch) -> None:
    tool = _load_tool(monkeypatch, tmp_path)
    artifact = tmp_path / "report.xlsx"
    artifact.write_bytes(b"PK\x03\x04 fake workbook")

    result = _json(
        tool.media_delivery_contract_tool(
            {
                "artifact_path": str(artifact),
                "caption": "검수된 엑셀 파일입니다.",
            }
        )
    )

    assert result["success"] is True
    assert result["artifact_path"] == str(artifact.resolve())
    assert result["media_tag"] == f"MEDIA:`{artifact.resolve()}`"
    assert result["delivery_text"].startswith("검수된 엑셀 파일입니다.")
    assert result["media_tag"] in result["delivery_text"]
    assert result["reviewer"]["name"] == "attachment_delivery_review"
    assert result["reviewer"]["status"] == "pass"
    assert {"artifact_path", "media_tag"}.issubset(result["reviewer"]["checked"])


def test_media_delivery_contract_fails_plainly_for_missing_file(tmp_path, monkeypatch) -> None:
    tool = _load_tool(monkeypatch, tmp_path)

    result = _json(
        tool.media_delivery_contract_tool(
            {
                "artifact_path": str(tmp_path / "missing.pdf"),
                "caption": "첨부 파일입니다.",
            }
        )
    )

    assert result["success"] is False
    assert result["reviewer"]["status"] == "fail"
    assert "파일" in result["message_ko"]
    assert "Traceback" not in json.dumps(result, ensure_ascii=False)


def test_media_delivery_contract_is_available_to_discord_toolset(tmp_path, monkeypatch) -> None:
    tool = _load_tool(monkeypatch, tmp_path)

    from tools.registry import registry

    entry = registry.get_entry("media_delivery_contract")
    assert entry is not None
    assert entry.toolset == "governance"
    assert tool.check_media_delivery_contract_requirements() is True
    assert "media_delivery_contract" in resolve_toolset("miho-discord")


def test_media_delivery_contract_quotes_nonstandard_extensions(tmp_path, monkeypatch) -> None:
    tool = _load_tool(monkeypatch, tmp_path)
    artifact = tmp_path / "report.mhtml"
    artifact.write_text("mime html archive", encoding="utf-8")

    result = _json(tool.media_delivery_contract_tool({"artifact_path": str(artifact)}))

    assert result["success"] is True
    assert result["media_tag"] == f"MEDIA:`{artifact.resolve()}`"


def test_media_delivery_contract_repairs_existing_file_outside_allowed_root(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    monkeypatch.setenv("MIHO_MEDIA_ALLOW_DIRS", str(tmp_path / "allowed"))

    import gateway.platforms.base as base
    import miho_constants
    import tools.media_delivery_contract_tool as tool

    importlib.reload(miho_constants)
    importlib.reload(base)
    importlib.reload(tool)

    artifact = tmp_path / "workspace" / "report.xlsx"
    artifact.parent.mkdir()
    artifact.write_bytes(b"PK\x03\x04 fake workbook")

    result = _json(
        tool.media_delivery_contract_tool(
            {
                "artifact_path": str(artifact),
                "caption": "복구된 첨부 파일입니다.",
            }
        )
    )

    assert result["success"] is True
    assert result["delivery_repair"]["status"] == "repaired"
    assert result["artifact_path"].startswith(str(tmp_path / "miho_home" / "cache" / "media"))
    assert result["media_tag"] == f"MEDIA:`{result['artifact_path']}`"
    assert base.resolve_media_delivery_path(result["artifact_path"]) == result["artifact_path"]
    assert "복구된 첨부 파일입니다." in result["delivery_text"]
