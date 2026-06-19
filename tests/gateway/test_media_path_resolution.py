"""Tests for resolving generated media paths before attachment upload."""

from gateway.platforms.base import BasePlatformAdapter


def _patch_roots(monkeypatch, *roots):
    monkeypatch.setattr(
        "gateway.platforms.base.MEDIA_DELIVERY_SAFE_ROOTS",
        tuple(roots),
    )


def test_filter_resolves_media_basename_from_safe_root(tmp_path, monkeypatch):
    root = tmp_path / "doc-cache"
    report = root / "report.pdf"
    root.mkdir()
    report.write_bytes(b"%PDF-1.4")
    _patch_roots(monkeypatch, root)

    filtered = BasePlatformAdapter.filter_media_delivery_paths([
        ("report.pdf", False),
    ])

    assert filtered == [(str(report.resolve()), False)]


def test_filter_resolves_relative_path_from_metadata_root(tmp_path, monkeypatch):
    safe_root = tmp_path / "empty-cache"
    workspace = tmp_path / "thread-workspace"
    report = workspace / "exports" / "report.pdf"
    safe_root.mkdir()
    report.parent.mkdir(parents=True)
    report.write_bytes(b"%PDF-1.4")
    _patch_roots(monkeypatch, safe_root)

    filtered = BasePlatformAdapter.filter_local_delivery_paths(
        ["exports/report.pdf"],
        metadata={"media_delivery_roots": [str(workspace)]},
    )

    assert filtered == [str(report.resolve())]


def test_media_tag_accepts_relative_file_names_for_safe_resolution():
    media, cleaned = BasePlatformAdapter.extract_media("완료\nMEDIA:report.pdf")

    assert media == [("report.pdf", False)]
    assert "MEDIA:" not in cleaned


def test_existing_unsafe_absolute_path_does_not_fall_back_by_basename(tmp_path, monkeypatch):
    safe_root = tmp_path / "safe-cache"
    safe_root.mkdir()
    (safe_root / "report.pdf").write_bytes(b"%PDF-1.4")
    unsafe = tmp_path / "outside" / "report.pdf"
    unsafe.parent.mkdir()
    unsafe.write_bytes(b"%PDF-1.4")
    _patch_roots(monkeypatch, safe_root)

    filtered = BasePlatformAdapter.filter_media_delivery_paths([
        (str(unsafe), False),
    ])

    assert filtered == []
