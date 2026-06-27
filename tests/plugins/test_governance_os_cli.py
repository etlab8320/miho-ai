"""Governance OS operator CLI tests."""

from __future__ import annotations

import argparse
import json

from plugins.governance_os import cli


def test_governance_cli_registers_expected_actions() -> None:
    parser = argparse.ArgumentParser(prog="miho governance")

    cli.register_cli(parser)
    args = parser.parse_args(["--json", "hooks"])

    assert args.governance_action == "hooks"
    assert args.json is True
    assert args.func is cli.governance_command


def test_governance_cli_accepts_json_after_action() -> None:
    parser = argparse.ArgumentParser(prog="miho governance")

    cli.register_cli(parser)
    args = parser.parse_args(["status", "--json"])

    assert args.governance_action == "status"
    assert args.json is True
    assert args.func is cli.governance_command


def test_governance_cli_prints_json_payload(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_governance_payload",
        lambda action: {"action": action, "readiness": {"ready": True}},
    )

    result = cli.governance_command(argparse.Namespace(governance_action="status", json=True))

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"action": "status", "readiness": {"ready": True}}


def test_governance_plugin_payload_uses_explicit_hook_counts(monkeypatch) -> None:
    class _Manager:
        _cli_commands = {"governance": {"name": "governance"}}
        _hooks = {
            "pre_gateway_dispatch": [object(), object()],
            "transform_llm_output": [object()],
        }

        def list_plugins(self) -> list[dict[str, object]]:
            return [
                {
                    "key": "governance_os",
                    "enabled": True,
                    "error": "",
                    "commands": 0,
                    "kind": "backend",
                    "version": "0.1.0",
                }
            ]

    monkeypatch.setattr("miho_cli.plugins.discover_plugins", lambda: None)
    monkeypatch.setattr("miho_cli.plugins.get_plugin_manager", lambda: _Manager())
    monkeypatch.setattr(cli, "_manifest_cli_commands", lambda: ["governance"])

    payload = cli._plugin_payload()

    assert "hooks" not in payload
    assert payload["registered_hook_groups"] == 2
    assert payload["registered_hook_callbacks"] == 3
    assert payload["manifest_cli_commands"] == ["governance"]


def test_governance_cli_prints_human_status(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_governance_payload",
        lambda action: {"readiness": {"ready": True}, "autopilot": {"registered": True}},
    )

    result = cli.governance_command(argparse.Namespace(governance_action=None, json=False))

    assert result == 0
    output = capsys.readouterr().out
    assert "Governance OS status" in output
    assert "ready: True" in output
    assert "registered: True" in output
