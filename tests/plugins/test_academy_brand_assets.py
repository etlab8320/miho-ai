"""Tests for bundled academy brand assets."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.academy_ops import brand_assets
from plugins.academy_ops import brand_logo_tool


_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_academy_brand_logo_uses_env_override(monkeypatch, tmp_path: Path) -> None:
    logo = tmp_path / "custom.png"
    logo.write_bytes(b"png")

    monkeypatch.setenv(brand_assets.BRAND_LOGO_ENV, str(logo))

    assert brand_assets.academy_brand_logo_path() == logo


def test_academy_brand_logo_falls_back_to_bundled_stamp(monkeypatch) -> None:
    monkeypatch.delenv(brand_assets.BRAND_LOGO_ENV, raising=False)

    logo = brand_assets.academy_brand_logo_path()

    assert logo == brand_assets.BUNDLED_STAMP_PATH
    assert logo.exists()
    assert logo.name == "stamp.png"


def test_academy_brand_logo_src_embeds_logo_data(monkeypatch, tmp_path: Path) -> None:
    logo = tmp_path / "custom.png"
    logo.write_bytes(b"png")
    monkeypatch.setenv(brand_assets.BRAND_LOGO_ENV, str(logo))

    src = brand_assets.academy_brand_logo_src()

    assert src == "data:image/png;base64,cG5n"


def test_stored_academy_logo_takes_priority_over_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "home"))
    env_logo = tmp_path / "env.png"
    env_logo.write_bytes(_PNG_BYTES)
    monkeypatch.setenv(brand_assets.BRAND_LOGO_ENV, str(env_logo))

    stored = brand_assets.save_academy_logo("7", _PNG_BYTES)

    assert brand_assets.academy_brand_logo_path("7") == stored
    assert stored.name == "7.png"


def test_academy_logo_falls_back_when_academy_has_none(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "home"))
    monkeypatch.delenv(brand_assets.BRAND_LOGO_ENV, raising=False)

    # An academy with no stored logo must fall back to the bundled stamp.
    assert brand_assets.academy_brand_logo_path("999") == brand_assets.BUNDLED_STAMP_PATH


def test_save_academy_logo_rejects_non_image(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "home"))

    try:
        brand_assets.save_academy_logo("7", b"this is not an image")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for non-image bytes")


def test_save_academy_logo_rejects_oversized(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "home"))
    oversized = _PNG_BYTES + b"\x00" * (brand_assets.MAX_LOGO_BYTES + 1)

    try:
        brand_assets.save_academy_logo("7", oversized)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for oversized image")


def test_delete_academy_logo_restores_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "home"))
    monkeypatch.delenv(brand_assets.BRAND_LOGO_ENV, raising=False)
    brand_assets.save_academy_logo("7", _PNG_BYTES)

    assert brand_assets.delete_academy_logo("7") is True
    assert brand_assets.stored_academy_logo_path("7") is None
    assert brand_assets.academy_brand_logo_path("7") == brand_assets.BUNDLED_STAMP_PATH


def test_set_brand_logo_tool_saves_attached_image(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "home"))

    result = json.loads(
        brand_logo_tool._academy_set_brand_logo_tool_handler(
            {}, academy_id="7", image_bytes=_PNG_BYTES
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "brand.logo_set"
    assert brand_assets.stored_academy_logo_path("7") is not None
    assert brand_assets.academy_brand_logo_path("7") == Path(result["logo_path"])


def test_set_brand_logo_tool_requires_attachment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "home"))

    result = json.loads(
        brand_logo_tool._academy_set_brand_logo_tool_handler(
            {}, academy_id="7", image_bytes=b""
        )
    )

    assert result["ok"] is False


def test_reset_brand_logo_tool_removes_stored_logo(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "home"))
    brand_assets.save_academy_logo("7", _PNG_BYTES)

    result = json.loads(
        brand_logo_tool._academy_reset_brand_logo_tool_handler({}, academy_id="7")
    )

    assert result["ok"] is True
    assert result["removed"] is True
    assert brand_assets.stored_academy_logo_path("7") is None
