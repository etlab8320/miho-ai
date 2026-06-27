"""Operator CLI for Miho Governance OS."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .operations import GovernanceReadinessReport, run_readiness_check
from .self_harness_cron import CRON_JOB_NAME


def register_cli(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    subcommands = subparser.add_subparsers(dest="governance_action")
    _add_action(subcommands, "status", "Show live Governance OS status")
    _add_action(subcommands, "readiness", "Run readiness checks")
    _add_action(subcommands, "hooks", "Show registered governance hooks")
    _add_action(subcommands, "failures", "Show readiness failures")
    _add_action(subcommands, "autopilot", "Show Self-Harness autopilot cron status")
    subparser.set_defaults(func=governance_command)


def governance_command(args: argparse.Namespace) -> int:
    action = str(getattr(args, "governance_action", None) or "status")
    payload = _governance_payload(action)
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    _print_payload(action, payload)
    return 0


def _governance_payload(action: str) -> dict[str, Any]:
    readiness = _readiness_payload(run_readiness_check())
    if action == "readiness":
        return {"readiness": readiness}
    if action == "hooks":
        return {"hooks": _hooks_payload()}
    if action == "failures":
        return {"failures": readiness["failures"]}
    if action == "autopilot":
        return {"autopilot": _autopilot_payload()}
    return {
        "plugin": _plugin_payload(),
        "readiness": readiness,
        "hooks": _hooks_payload(),
        "autopilot": _autopilot_payload(),
    }


def _add_action(subcommands: Any, name: str, help_text: str) -> None:
    parser = subcommands.add_parser(name, help=help_text)
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Print machine-readable JSON",
    )


def _readiness_payload(report: GovernanceReadinessReport) -> dict[str, Any]:
    raw = asdict(report)
    return {
        "ready": raw["ready"],
        "quality_score": raw["quality_score"],
        "full_system_ready": raw["full_system_ready"],
        "full_system_score": raw["full_system_score"],
        "live_discord_verified": raw["live_discord_verified"],
        "validation_loop_smoke_mode": raw["validation_loop_smoke_mode"],
        "rollback_status": raw["rollback_status"],
        "active_snapshot_id": raw["active_snapshot_id"],
        "failures": list(raw["failures"]),
    }


def _plugin_payload() -> dict[str, Any]:
    try:
        from miho_cli.plugins import discover_plugins, get_plugin_manager

        discover_plugins()
        manager = get_plugin_manager()
        plugins = {item["key"]: item for item in manager.list_plugins()}
        cli_commands = getattr(manager, "_cli_commands", {})
        hooks = getattr(manager, "_hooks", {})
    except Exception as exc:
        return {"enabled": False, "error": str(exc)}
    plugin = plugins.get("governance_os") or {}
    governance_cli = cli_commands.get("governance") if isinstance(cli_commands, dict) else None
    hook_groups = _registered_hook_group_count(hooks)
    callback_count = _registered_hook_callback_count(hooks)
    return {
        "enabled": bool(plugin.get("enabled")),
        "error": str(plugin.get("error") or ""),
        "registered_hook_groups": hook_groups,
        "registered_hook_callbacks": callback_count,
        "commands": int(plugin.get("commands") or 0),
        "cli_commands": int(bool(governance_cli)),
        "operator_cli": bool(governance_cli),
        "manifest_cli_commands": _manifest_cli_commands(),
        "kind": str(plugin.get("kind") or ""),
        "version": str(plugin.get("version") or ""),
    }


def _hooks_payload() -> dict[str, Any]:
    expected = (
        "pre_gateway_dispatch",
        "pre_tool_call",
        "transform_tool_result",
        "transform_llm_output",
    )
    try:
        from miho_cli.plugins import discover_plugins, get_plugin_manager

        discover_plugins()
        hooks = getattr(get_plugin_manager(), "_hooks", {})
    except Exception as exc:
        return {name: {"registered": False, "error": str(exc)} for name in expected}
    return {
        name: {
            "registered": bool(hooks.get(name)),
            "callbacks": _callback_modules(hooks.get(name, ())),
        }
        for name in expected
    }


def _callback_modules(callbacks: Any) -> list[str]:
    modules: list[str] = []
    for callback in callbacks or ():
        module = str(getattr(callback, "__module__", ""))
        name = str(getattr(callback, "__name__", repr(callback)))
        modules.append(f"{module}.{name}" if module else name)
    return modules


def _registered_hook_group_count(hooks: Any) -> int:
    if not isinstance(hooks, dict):
        return 0
    return sum(1 for callbacks in hooks.values() if callbacks)


def _registered_hook_callback_count(hooks: Any) -> int:
    if not isinstance(hooks, dict):
        return 0
    return sum(len(callbacks or ()) for callbacks in hooks.values())


def _manifest_cli_commands() -> list[str]:
    try:
        import yaml

        manifest_path = Path(__file__).with_name("plugin.yaml")
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, dict):
        return []
    commands = raw.get("provides_cli_commands")
    if not isinstance(commands, list):
        return []
    return [str(command).strip() for command in commands if str(command).strip()]


def _autopilot_payload() -> dict[str, Any]:
    try:
        from cron.jobs import list_jobs

        jobs = list_jobs(include_disabled=True)
    except Exception as exc:
        return {"registered": False, "error": str(exc)}
    for job in jobs:
        if str(job.get("name") or "") != CRON_JOB_NAME:
            continue
        return {
            "registered": True,
            "enabled": bool(job.get("enabled", True)),
            "schedule": str(job.get("schedule") or ""),
            "next_run_at": str(job.get("next_run_at") or ""),
            "last_run_at": str(job.get("last_run_at") or ""),
            "last_status": str(job.get("last_status") or ""),
        }
    return {"registered": False, "enabled": False}


def _print_payload(action: str, payload: dict[str, Any]) -> None:
    print(f"Governance OS {action}")
    for key, value in payload.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for subkey, subvalue in value.items():
                print(f"  {subkey}: {subvalue}")
        else:
            print(f"{key}: {value}")
