"""Tests for bundled academy brand assets."""

from __future__ import annotations

from pathlib import Path

from plugins.academy_ops import brand_assets


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
