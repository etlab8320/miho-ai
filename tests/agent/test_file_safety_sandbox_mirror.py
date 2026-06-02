"""Tests for Miho sandbox-mirror write guards."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


def _mirror_target(tmp_path: Path) -> Path:
    return (
        tmp_path
        / "profiles"
        / "group1"
        / "sandboxes"
        / "docker"
        / "default"
        / "home"
        / ".miho"
        / "profiles"
        / "group1"
        / "SOUL.md"
    )


def test_sandbox_mirror_path_classified(tmp_path):
    from agent.file_safety import classify_sandbox_mirror_target

    target = _mirror_target(tmp_path)
    target.parent.mkdir(parents=True)

    result = classify_sandbox_mirror_target(str(target))

    assert result is not None
    assert result["target_path"] == str(target.resolve())
    assert result["mirror_root"].endswith("sandboxes/docker/default/home/.miho")
    assert result["inner_path"] == "profiles/group1/SOUL.md"


def test_plain_miho_path_not_classified(tmp_path):
    from agent.file_safety import classify_sandbox_mirror_target

    target = tmp_path / ".miho" / "profiles" / "group1" / "SOUL.md"
    target.parent.mkdir(parents=True)

    assert classify_sandbox_mirror_target(str(target)) is None


def test_write_file_blocks_sandbox_mirror_before_file_ops(tmp_path, monkeypatch):
    import tools.file_tools as ft

    target = _mirror_target(tmp_path)
    target.parent.mkdir(parents=True)
    monkeypatch.setattr(ft, "_get_file_ops", lambda *_args, **_kw: None)

    result = json.loads(ft.write_file_tool(str(target), "x"))

    assert "error" in result
    assert "Sandbox-mirror write blocked" in result["error"]
    assert "Miho process never reads" in result["error"]


def test_write_file_cross_profile_bypass_preserves_write_path(tmp_path, monkeypatch):
    import tools.file_tools as ft

    class FakeFileOps:
        def write_file(self, path: str, content: str):
            assert path == str(target)
            assert content == "x"
            return SimpleNamespace(to_dict=lambda: {"bytes_written": 1})

    target = _mirror_target(tmp_path)
    target.parent.mkdir(parents=True)
    monkeypatch.setattr(ft, "_get_file_ops", lambda *_args, **_kw: FakeFileOps())

    result = json.loads(
        ft.write_file_tool(str(target), "x", cross_profile=True)
    )

    assert result == {"bytes_written": 1}


def test_patch_blocks_sandbox_mirror_path(tmp_path, monkeypatch):
    import tools.file_tools as ft

    target = _mirror_target(tmp_path)
    target.parent.mkdir(parents=True)
    monkeypatch.setattr(ft, "_get_file_ops", lambda *_args, **_kw: None)

    result = json.loads(
        ft.patch_tool(
            mode="replace",
            path=str(target),
            old_string="old",
            new_string="new",
        )
    )

    assert "error" in result
    assert "Sandbox-mirror write blocked" in result["error"]
