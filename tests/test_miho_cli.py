"""Tests for the Miho AI console-script wrapper."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType


def test_miho_version_uses_miho_brand(monkeypatch, capsys):
    from miho_cli import entry

    monkeypatch.setattr(sys, "argv", ["miho", "--version"])
    monkeypatch.setattr(Path, "home", lambda: Path("/tmp/test-home"))
    monkeypatch.delenv("MIHO_HOME", raising=False)

    entry.main()

    output = capsys.readouterr().out
    assert "Miho AI v" in output
    assert "Runtime: Miho native" in output
    assert "Miho home: /tmp/test-home/.miho" in output


def test_miho_entrypoint_sets_native_runtime(monkeypatch):
    from miho_cli import entry

    called = {"main": False}
    fake_pkg = ModuleType("miho_cli")
    fake_main = ModuleType("miho_cli.main")

    def main() -> None:
        called["main"] = True

    fake_main.main = main
    monkeypatch.setitem(sys.modules, "miho_cli", fake_pkg)
    monkeypatch.setitem(sys.modules, "miho_cli.main", fake_main)
    monkeypatch.delenv("MIHO_DEFAULT_SKIN", raising=False)
    monkeypatch.delenv("MIHO_RUNTIME", raising=False)
    monkeypatch.delenv("MIHO_BRAND", raising=False)
    monkeypatch.delenv("MIHO_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: Path("/tmp/test-home"))

    entry.main()

    assert called["main"] is True
    assert sys.modules["miho_cli.main"] is fake_main
    assert "1" == __import__("os").environ["MIHO_RUNTIME"]
    assert "miho" == __import__("os").environ["MIHO_BRAND"]
    assert "/tmp/test-home/.miho" == __import__("os").environ["MIHO_HOME"]
    assert "MIHO_DEFAULT_SKIN" not in __import__("os").environ


def test_miho_entrypoint_preserves_native_home(monkeypatch):
    from miho_cli import entry

    fake_pkg = ModuleType("miho_cli")
    fake_main = ModuleType("miho_cli.main")
    fake_main.main = lambda: None
    monkeypatch.setitem(sys.modules, "miho_cli", fake_pkg)
    monkeypatch.setitem(sys.modules, "miho_cli.main", fake_main)
    monkeypatch.setenv("MIHO_HOME", "/tmp/custom-miho")

    entry.main()

    assert __import__("os").environ["MIHO_HOME"] == "/tmp/custom-miho"
    assert __import__("os").environ["MIHO_RUNTIME"] == "1"


def test_miho_entrypoint_uses_explicit_miho_home(monkeypatch):
    from miho_cli import entry

    fake_pkg = ModuleType("miho_cli")
    fake_main = ModuleType("miho_cli.main")
    fake_main.main = lambda: None
    monkeypatch.setitem(sys.modules, "miho_cli", fake_pkg)
    monkeypatch.setitem(sys.modules, "miho_cli.main", fake_main)
    monkeypatch.setenv("MIHO_HOME", "/tmp/miho-native")

    entry.main()

    assert __import__("os").environ["MIHO_HOME"] == "/tmp/miho-native"
