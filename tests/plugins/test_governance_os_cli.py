"""Governance OS operator CLI tests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from plugins.governance_os import cli
from plugins.governance_os.autopilot_status import build_autopilot_status


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


def test_governance_cli_registers_quality_and_live_check_actions() -> None:
    parser = argparse.ArgumentParser(prog="miho governance")

    cli.register_cli(parser)
    quality_args = parser.parse_args(["quality", "--json"])
    live_args = parser.parse_args(
        ["live-check", "--mode", "live", "--target", "discord:123:456", "--json"]
    )

    assert quality_args.governance_action == "quality"
    assert quality_args.json is True
    assert live_args.governance_action == "live-check"
    assert live_args.mode == "live"
    assert live_args.target == "discord:123:456"
    assert live_args.json is True


def test_governance_cli_prints_json_payload(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_governance_payload",
        lambda action, **_kwargs: {"action": action, "readiness": {"ready": True}},
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


def test_governance_payload_exposes_self_harness_quality(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_readiness_payload", lambda _report: {"ready": True, "quality_score": 100})
    monkeypatch.setattr(cli, "run_readiness_check", lambda: object())
    monkeypatch.setattr(cli, "_plugin_payload", lambda: {"enabled": True})
    monkeypatch.setattr(cli, "_hooks_payload", lambda: {})
    monkeypatch.setattr(
        cli,
        "_autopilot_payload",
        lambda: {"registered": True, "ready": False, "progress_state": "attention_needed"},
    )
    monkeypatch.setattr(
        cli,
        "_self_harness_quality_payload",
        lambda: {"ready": False, "score": 88},
    )

    payload = cli._governance_payload("status")

    assert payload["self_harness_quality"] == {"ready": False, "score": 88}
    assert payload["operational_summary"] == {
        "status": "operational_ready_but_quality_debt",
        "readiness_ready": True,
        "readiness_quality_score": 100,
        "self_harness_quality_ready": False,
        "self_harness_quality_score": 88,
        "full_system_ready": False,
        "readiness_full_system_ready": False,
        "full_system_score": 0,
        "actual_discord_send_verified": False,
        "self_harness_runtime_learning_ready": True,
        "autopilot_ready": False,
        "autopilot_progress_state": "attention_needed",
    }


def test_operational_summary_refuses_full_ready_when_autopilot_needs_attention() -> None:
    summary = cli._operational_summary(
        {
            "ready": True,
            "quality_score": 100,
            "full_system_ready": True,
            "full_system_score": 100,
            "actual_discord_send_verified": True,
            "self_harness_runtime_learning_ready": True,
        },
        {"ready": True, "score": 100},
        {"registered": True, "ready": False, "progress_state": "attention_needed"},
    )

    assert summary["status"] == "operational_ready_but_autopilot_debt"
    assert summary["autopilot_ready"] is False
    assert summary["full_system_ready"] is False
    assert summary["readiness_full_system_ready"] is True


def test_autopilot_status_reads_latest_run_receipt(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "output"
    job_dir = output_dir / "job-1"
    job_dir.mkdir(parents=True)
    (job_dir / "2026-06-28_04-01-56.md").write_text(
        "# Cron Job\n\n"
        + json.dumps(
            {
                "candidate_count": 2,
                "activated": [],
                "rolled_back": [],
                "held": [{"reason": "validation_incomplete"}],
                "skipped_unsafe": [],
                "errors": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    import cron.jobs as cron_jobs

    monkeypatch.setattr(cron_jobs, "OUTPUT_DIR", Path(output_dir))
    monkeypatch.setattr(
        cron_jobs,
        "list_jobs",
        lambda include_disabled=False: [
            {
                "id": "job-1",
                "name": "governance_self_harness_autopilot",
                "enabled": True,
                "schedule_display": "0 4 * * *",
                "next_run_at": "2026-06-29T04:00:00+09:00",
                "last_run_at": "2026-06-28T04:01:56+09:00",
                "last_status": "ok",
            }
        ],
    )

    payload = build_autopilot_status()

    assert payload["registered"] is True
    assert payload["ready"] is False
    assert payload["progress_state"] == "attention_needed"
    assert payload["last_receipt"]["candidate_count"] == 2
    assert payload["last_receipt"]["held_reasons"] == ["validation_incomplete"]


def test_governance_live_check_payload_uses_operational_validation(monkeypatch) -> None:
    monkeypatch.setattr(cli, "_readiness_payload", lambda _report: {"ready": True})
    monkeypatch.setattr(cli, "run_readiness_check", lambda: object())
    monkeypatch.setattr(
        cli,
        "_operational_validation_payload",
        lambda mode, target: {"ready": True, "mode": mode, "target": target},
    )

    payload = cli._governance_payload(
        "live-check",
        args=argparse.Namespace(mode="live", target="discord:123:456"),
    )

    assert payload["operational_validation"] == {
        "ready": True,
        "mode": "live",
        "target": "discord:123:456",
    }


def test_governance_cli_prints_human_status(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        cli,
        "_governance_payload",
        lambda action, **_kwargs: {
            "readiness": {"ready": True},
            "autopilot": {"registered": True},
        },
    )

    result = cli.governance_command(argparse.Namespace(governance_action=None, json=False))

    assert result == 0
    output = capsys.readouterr().out
    assert "Governance OS status" in output
    assert "ready: True" in output
    assert "registered: True" in output
