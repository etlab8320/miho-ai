from datetime import datetime, timezone
import os
from pathlib import Path

import pytest

from gateway.media_cache_manager import cleanup_media_cache, managed_media_dir


def test_managed_media_dir_uses_category_and_utc_date(tmp_path, monkeypatch):
    miho_home = tmp_path / ".miho"
    monkeypatch.setenv("MIHO_HOME", str(miho_home))
    when = datetime(2026, 6, 21, 3, 4, tzinfo=timezone.utc)

    path = managed_media_dir("Gateway Promoted!", when=when)

    assert path == miho_home / "cache" / "media" / "gateway_promoted" / "20260621"
    assert path.is_dir()


def test_cleanup_media_cache_dry_run_keeps_old_files(tmp_path, monkeypatch):
    miho_home = tmp_path / ".miho"
    monkeypatch.setenv("MIHO_HOME", str(miho_home))
    old_file = miho_home / "cache" / "media" / "academy_reports" / "old.pdf"
    old_file.parent.mkdir(parents=True)
    old_file.write_bytes(b"old")
    old_time = datetime(2026, 5, 1, tzinfo=timezone.utc).timestamp()
    os.utime(old_file, (old_time, old_time))

    summary = cleanup_media_cache(
        retention_days=14,
        dry_run=True,
        now=datetime(2026, 6, 21, tzinfo=timezone.utc),
    )

    assert summary.candidate_files == 1
    assert summary.deleted_files == 0
    assert summary.freed_bytes == 3
    assert old_file.exists()


def test_cleanup_media_cache_deletes_old_files_and_empty_dirs(tmp_path, monkeypatch):
    miho_home = tmp_path / ".miho"
    monkeypatch.setenv("MIHO_HOME", str(miho_home))
    old_file = miho_home / "cache" / "media" / "academy_reports" / "20260501" / "old.pdf"
    fresh_file = miho_home / "cache" / "media" / "academy_reports" / "20260620" / "fresh.pdf"
    old_file.parent.mkdir(parents=True)
    fresh_file.parent.mkdir(parents=True)
    old_file.write_bytes(b"old")
    fresh_file.write_bytes(b"fresh")
    old_ts = datetime(2026, 5, 1, tzinfo=timezone.utc).timestamp()
    fresh_ts = datetime(2026, 6, 20, tzinfo=timezone.utc).timestamp()

    os.utime(old_file, (old_ts, old_ts))
    os.utime(fresh_file, (fresh_ts, fresh_ts))

    summary = cleanup_media_cache(
        retention_days=14,
        dry_run=False,
        now=datetime(2026, 6, 21, tzinfo=timezone.utc),
    )

    assert summary.deleted_files == 1
    assert summary.deleted_dirs >= 1
    assert not old_file.exists()
    assert fresh_file.exists()


def test_cleanup_media_cache_rejects_unsafe_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / ".miho"))

    with pytest.raises(ValueError):
        cleanup_media_cache(roots=[Path("/tmp")])
