"""Tests for the Miho AI console-script wrapper."""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType


def test_miho_version_uses_miho_brand(monkeypatch, capsys):
    import miho_cli

    monkeypatch.setattr(sys, "argv", ["miho", "--version"])
    monkeypatch.setattr(Path, "home", lambda: Path("/tmp/test-home"))
    monkeypatch.delenv("MIHO_HOME", raising=False)

    miho_cli.main()

    output = capsys.readouterr().out
    assert "Miho AI v" in output
    assert "Engine: Hermes Agent" in output
    assert "Miho home: /tmp/test-home/.miho" in output


def test_miho_entrypoint_sets_default_skin(monkeypatch):
    import miho_cli

    called = {"main": False}
    fake_pkg = ModuleType("hermes_cli")
    fake_main = ModuleType("hermes_cli.main")

    def main() -> None:
        called["main"] = True

    fake_main.main = main
    monkeypatch.setitem(sys.modules, "hermes_cli", fake_pkg)
    monkeypatch.setitem(sys.modules, "hermes_cli.main", fake_main)
    monkeypatch.delenv("HERMES_DEFAULT_SKIN", raising=False)
    monkeypatch.delenv("HERMES_BRAND", raising=False)
    monkeypatch.delenv("MIHO_HOME", raising=False)
    monkeypatch.setattr(Path, "home", lambda: Path("/tmp/test-home"))

    miho_cli.main()

    assert called["main"] is True
    assert sys.modules["hermes_cli.main"] is fake_main
    assert "miho" == __import__("os").environ["HERMES_DEFAULT_SKIN"]
    assert "miho" == __import__("os").environ["HERMES_BRAND"]
    assert "/tmp/test-home/.miho" == __import__("os").environ["MIHO_HOME"]
    assert "/tmp/test-home/.miho" == __import__("os").environ["HERMES_HOME"]


def test_miho_entrypoint_preserves_explicit_skin(monkeypatch):
    import miho_cli

    fake_pkg = ModuleType("hermes_cli")
    fake_main = ModuleType("hermes_cli.main")
    fake_main.main = lambda: None
    monkeypatch.setitem(sys.modules, "hermes_cli", fake_pkg)
    monkeypatch.setitem(sys.modules, "hermes_cli.main", fake_main)
    monkeypatch.setenv("HERMES_DEFAULT_SKIN", "ares")
    monkeypatch.setenv("MIHO_HOME", "/tmp/custom-miho")

    miho_cli.main()

    assert __import__("os").environ["HERMES_DEFAULT_SKIN"] == "ares"
    assert __import__("os").environ["HERMES_HOME"] == "/tmp/custom-miho"


def test_miho_entrypoint_ignores_external_hermes_home(monkeypatch):
    import miho_cli

    fake_pkg = ModuleType("hermes_cli")
    fake_main = ModuleType("hermes_cli.main")
    fake_main.main = lambda: None
    monkeypatch.setitem(sys.modules, "hermes_cli", fake_pkg)
    monkeypatch.setitem(sys.modules, "hermes_cli.main", fake_main)
    monkeypatch.setenv("MIHO_HOME", "/tmp/miho-native")
    monkeypatch.setenv("HERMES_HOME", "/tmp/hermes-should-not-win")

    miho_cli.main()

    assert __import__("os").environ["MIHO_HOME"] == "/tmp/miho-native"
    assert __import__("os").environ["HERMES_HOME"] == "/tmp/miho-native"
