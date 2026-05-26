"""Regression tests for Miho ZIP updater archive safety."""

from __future__ import annotations

import os
import stat
import tempfile
import zipfile
from unittest.mock import patch

import pytest


def _build_zip_with_symlink_member(zip_path: str, link_name: str, target: str) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        info = zipfile.ZipInfo(link_name)
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, target)


def test_update_via_zip_rejects_symlink_member(tmp_path):
    zip_path = tmp_path / "evil.zip"
    _build_zip_with_symlink_member(
        str(zip_path),
        link_name="miho-agent-main/evil-link",
        target="/etc/passwd",
    )

    from miho_cli.main import _update_via_zip

    captured: dict[str, str] = {}
    original_mkdtemp = tempfile.mkdtemp

    def capturing_mkdtemp(*args, **kwargs):
        directory = original_mkdtemp(*args, **kwargs)
        captured["tmp_dir"] = directory
        return directory

    def fake_urlretrieve(url, dest):
        with open(zip_path, "rb") as src, open(dest, "wb") as dst:
            dst.write(src.read())
        return dest, None

    with patch("tempfile.mkdtemp", side_effect=capturing_mkdtemp), \
         patch("urllib.request.urlretrieve", side_effect=fake_urlretrieve):
        with pytest.raises(SystemExit) as exc_info:
            _update_via_zip(type("Args", (), {})())

    assert exc_info.value.code == 1
    tmp_dir = captured.get("tmp_dir")
    if tmp_dir:
        assert not os.path.lexists(
            os.path.join(tmp_dir, "miho-agent-main", "evil-link")
        )
