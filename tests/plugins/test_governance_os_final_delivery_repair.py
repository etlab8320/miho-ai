"""Final Delivery Repair executor contracts."""

from __future__ import annotations

import importlib

from plugins.governance_os.final_delivery_repair import repair_artifact_delivery


def _reload_media_base(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import gateway.platforms.base as base
    import miho_constants

    importlib.reload(miho_constants)
    importlib.reload(base)
    return base


def test_final_delivery_repair_stages_existing_file_outside_allowed_root(
    tmp_path,
    monkeypatch,
) -> None:
    base = _reload_media_base(tmp_path, monkeypatch)
    source_dir = tmp_path / "workspace"
    source_dir.mkdir()
    artifact = source_dir / "report.mhtml"
    artifact.write_text("html archive", encoding="utf-8")

    result = repair_artifact_delivery(str(artifact), caption="검수된 파일입니다.")

    assert result.status == "repaired"
    assert result.staged_path
    assert result.media_tag == f"MEDIA:`{result.staged_path}`"
    assert result.delivery_text.startswith("검수된 파일입니다.")
    assert artifact.read_text(encoding="utf-8") == "html archive"
    assert base.resolve_media_delivery_path(result.staged_path) == result.staged_path
    assert result.reviewer["status"] == "pass"
    assert "artifact_staged" in result.reviewer["checked"]


def test_final_delivery_repair_keeps_already_allowed_file(tmp_path, monkeypatch) -> None:
    base = _reload_media_base(tmp_path, monkeypatch)
    artifact = tmp_path / "miho_home" / "cache" / "media" / "already.pdf"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"%PDF")

    result = repair_artifact_delivery(str(artifact))

    assert result.status == "already_allowed"
    assert result.artifact_path == str(artifact.resolve())
    assert result.staged_path == ""
    assert base.resolve_media_delivery_path(result.artifact_path) == result.artifact_path


def test_final_delivery_repair_blocks_missing_file_plainly(tmp_path, monkeypatch) -> None:
    _reload_media_base(tmp_path, monkeypatch)

    result = repair_artifact_delivery(str(tmp_path / "missing.xlsx"))

    assert result.status == "blocked"
    assert result.media_tag == ""
    assert result.reviewer["status"] == "fail"
    assert "파일" in result.message_ko
    assert "Traceback" not in result.message_ko
