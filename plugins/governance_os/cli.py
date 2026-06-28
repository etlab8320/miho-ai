"""Operator CLI for Miho Governance OS."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .operations import GovernanceReadinessReport, run_readiness_check

def register_cli(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    subcommands = subparser.add_subparsers(dest="governance_action")
    _add_action(subcommands, "status", "Show live Governance OS status")
    _add_action(subcommands, "readiness", "Run readiness checks")
    _add_action(subcommands, "hooks", "Show registered governance hooks")
    _add_action(subcommands, "failures", "Show readiness failures")
    _add_action(subcommands, "autopilot", "Show Self-Harness autopilot cron status")
    _add_action(subcommands, "quality", "Show Self-Harness long-horizon quality")
    live_check = _add_action(subcommands, "live-check", "Run live-safe Discord and academy validation")
    live_check.add_argument("--mode", choices=("live_safe", "live"), default="live_safe")
    live_check.add_argument(
        "--target",
        default="",
        help="Discord live-smoke target, e.g. discord:channel_id:thread_id",
    )
    subparser.set_defaults(func=governance_command)


def governance_command(args: argparse.Namespace) -> int:
    action = str(getattr(args, "governance_action", None) or "status")
    payload = _governance_payload(action, args=args)
    if getattr(args, "json", False):
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    _print_payload(action, payload)
    return 0


def _governance_payload(action: str, *, args: argparse.Namespace | None = None) -> dict[str, Any]:
    readiness = _readiness_payload(run_readiness_check())
    if action == "readiness":
        return {"readiness": readiness}
    if action == "hooks":
        return {"hooks": _hooks_payload()}
    if action == "failures":
        return {"failures": readiness["failures"]}
    if action == "autopilot":
        return {"autopilot": _autopilot_payload()}
    if action == "quality":
        return {"self_harness_quality": _self_harness_quality_payload()}
    if action == "live-check":
        mode = str(getattr(args, "mode", "live_safe") or "live_safe")
        target = str(getattr(args, "target", "") or "")
        return {"operational_validation": _operational_validation_payload(mode=mode, target=target)}
    autopilot = _autopilot_payload()
    self_harness_quality = _self_harness_quality_payload()
    return {
        "plugin": _plugin_payload(),
        "readiness": readiness,
        "hooks": _hooks_payload(),
        "autopilot": autopilot,
        "self_harness_quality": self_harness_quality,
        "operational_summary": _operational_summary(
            readiness,
            self_harness_quality,
            autopilot,
        ),
    }


def _add_action(subcommands: Any, name: str, help_text: str) -> Any:
    parser = subcommands.add_parser(name, help=help_text)
    parser.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Print machine-readable JSON",
    )
    return parser


def _readiness_payload(report: GovernanceReadinessReport) -> dict[str, Any]:
    raw = asdict(report)
    smoke_mode = str(raw["validation_loop_smoke_mode"] or "")
    actual_send_verified = bool(raw["live_discord_verified"] and smoke_mode == "live")
    artifact_preflight_ready = bool(raw["validation_loop_probe_passed"] and smoke_mode in {"live", "live_safe"})
    return {
        "ready": raw["ready"],
        "quality_score": raw["quality_score"],
        "full_system_ready": raw["full_system_ready"],
        "full_system_score": raw["full_system_score"],
        "live_discord_verified": raw["live_discord_verified"],
        "actual_discord_send_verified": actual_send_verified,
        "discord_artifact_preflight_ready": artifact_preflight_ready,
        "readiness_scope": "actual_discord_send" if actual_send_verified else "live_safe_preflight",
        "validation_loop_smoke_mode": raw["validation_loop_smoke_mode"],
        "rollback_status": raw["rollback_status"],
        "active_snapshot_id": raw["active_snapshot_id"],
        "self_harness_runtime_learning_ready": raw[
            "self_harness_runtime_feedback_probe_passed"
        ],
        "failures": list(raw["failures"]),
    }


def _operational_summary(
    readiness: dict[str, Any],
    self_harness_quality: dict[str, Any],
    autopilot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readiness_ready = bool(readiness.get("ready"))
    quality_ready = bool(self_harness_quality.get("ready"))
    autopilot_payload = autopilot or {}
    autopilot_ready = bool(autopilot_payload.get("ready", autopilot_payload.get("registered", True)))
    readiness_full_system_ready = bool(readiness.get("full_system_ready"))
    full_system_ready = bool(
        readiness_ready
        and quality_ready
        and autopilot_ready
        and readiness_full_system_ready
    )
    runtime_learning_ready = bool(
        readiness.get("self_harness_runtime_learning_ready", readiness_ready)
    )
    if not readiness_ready:
        status = "readiness_failed"
    elif not quality_ready:
        status = "operational_ready_but_quality_debt"
    elif not autopilot_ready:
        status = "operational_ready_but_autopilot_debt"
    elif full_system_ready:
        status = "full_system_ready"
    else:
        status = "live_safe_ready"
    return {
        "status": status,
        "readiness_ready": readiness_ready,
        "readiness_quality_score": int(readiness.get("quality_score") or 0),
        "self_harness_quality_ready": quality_ready,
        "self_harness_quality_score": int(self_harness_quality.get("score") or 0),
        "full_system_ready": full_system_ready,
        "readiness_full_system_ready": readiness_full_system_ready,
        "full_system_score": int(readiness.get("full_system_score") or 0),
        "actual_discord_send_verified": bool(readiness.get("actual_discord_send_verified")),
        "self_harness_runtime_learning_ready": runtime_learning_ready,
        "autopilot_ready": autopilot_ready,
        "autopilot_progress_state": str(autopilot_payload.get("progress_state") or ""),
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
    from .autopilot_status import build_autopilot_status

    return build_autopilot_status()


def _self_harness_quality_payload() -> dict[str, Any]:
    from .self_harness_quality import build_self_harness_quality_report

    return build_self_harness_quality_report().to_payload()


def _operational_validation_payload(*, mode: str, target: str = "") -> dict[str, Any]:
    from .operational_validation import build_operational_validation_report

    clean_mode = "live" if mode == "live" else "live_safe"
    return build_operational_validation_report(mode=clean_mode, target=target).to_payload()


def _print_payload(action: str, payload: dict[str, Any]) -> None:
    print(f"Governance OS {action}")
    for key, value in payload.items():
        if isinstance(value, dict):
            print(f"{key}:")
            for subkey, subvalue in value.items():
                print(f"  {subkey}: {subvalue}")
        else:
            print(f"{key}: {value}")
