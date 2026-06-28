"""Live-safe operational validation for Governance OS."""

from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .discord_live_smoke import DiscordSmokeMode, SenderFn, build_discord_delivery_smoke
from .operations import run_readiness_check


@dataclass(frozen=True)
class OperationalValidationReport:
    ready: bool
    mode: DiscordSmokeMode
    readiness_ready: bool
    academy_accuracy_ready: bool
    discord_delivery_ready: bool
    gateway_process_ready: bool
    discord_artifact_preflight_ready: bool
    actual_discord_send_verified: bool
    live_discord_verified: bool
    artifact_path: str
    failures: tuple[str, ...] = field(default_factory=tuple)
    receipts: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "mode": self.mode,
            "readiness_ready": self.readiness_ready,
            "academy_accuracy_ready": self.academy_accuracy_ready,
            "discord_delivery_ready": self.discord_delivery_ready,
            "gateway_process_ready": self.gateway_process_ready,
            "discord_artifact_preflight_ready": self.discord_artifact_preflight_ready,
            "actual_discord_send_verified": self.actual_discord_send_verified,
            "live_discord_verified": self.live_discord_verified,
            "artifact_path": self.artifact_path,
            "failures": list(self.failures),
            "receipts": self.receipts,
        }


def build_operational_validation_report(
    *,
    mode: DiscordSmokeMode = "live_safe",
    target: str = "",
    sender: SenderFn | None = None,
) -> OperationalValidationReport:
    """Validate runtime protection with safe Discord and academy probes."""

    readiness = run_readiness_check()
    artifact_path = _ensure_probe_artifact()
    previous_allow_dirs = os.environ.get("MIHO_MEDIA_ALLOW_DIRS")
    os.environ["MIHO_MEDIA_ALLOW_DIRS"] = _with_media_allow_dir(previous_allow_dirs, artifact_path.parent)
    try:
        smoke = build_discord_delivery_smoke(
            artifact_path=str(artifact_path),
            mode=mode,
            target=target,
            caption="미호 Governance OS live-safe delivery validation.",
            sender=sender or _default_live_sender(mode=mode, target=target),
        )
    finally:
        if previous_allow_dirs is None:
            os.environ.pop("MIHO_MEDIA_ALLOW_DIRS", None)
        else:
            os.environ["MIHO_MEDIA_ALLOW_DIRS"] = previous_allow_dirs

    failures = list(readiness.failures)
    failures.extend(smoke.failures)
    academy_ready = bool(readiness.academy_accuracy_probe_passed)
    if not academy_ready:
        failures.append("academy_accuracy_probe_failed")
    ready = bool(readiness.ready and academy_ready and smoke.ready)
    report = OperationalValidationReport(
        ready=ready,
        mode=mode,
        readiness_ready=readiness.ready,
        academy_accuracy_ready=academy_ready,
        discord_delivery_ready=smoke.ready,
        gateway_process_ready=smoke.gateway_process_ready,
        discord_artifact_preflight_ready=smoke.artifact_preflight_ready,
        actual_discord_send_verified=smoke.actual_send_verified,
        live_discord_verified=smoke.actual_send_verified,
        artifact_path=str(artifact_path),
        failures=tuple(dict.fromkeys(str(item) for item in failures if str(item).strip())),
        receipts={
            "preflight": smoke.preflight_receipt,
            "live_gateway": smoke.live_gateway_receipt,
            "attachment": smoke.attachment_receipt,
        },
    )
    if report.actual_discord_send_verified:
        _persist_live_smoke_receipt(report)
    return report


def _ensure_probe_artifact() -> Path:
    from miho_constants import get_miho_home

    path = get_miho_home() / "media_cache" / "governance_os_live_safe_probe.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n%%EOF\n")
    return path


def _default_live_sender(*, mode: DiscordSmokeMode, target: str) -> SenderFn | None:
    if mode != "live" or not str(target or "").strip():
        return None
    return _send_with_send_message_tool


def _send_with_send_message_tool(target: str, message: str) -> dict[str, Any]:
    try:
        from miho_cli.send_cmd import _load_miho_env

        _load_miho_env()
    except Exception:
        pass
    try:
        from tools.send_message_tool import send_message_tool

        raw = send_message_tool(
            {
                "action": "send",
                "target": target,
                "message": message,
            }
        )
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"success": False}
    except Exception:
        return {"success": False}
    return payload if isinstance(payload, dict) else {"success": False}


def _persist_live_smoke_receipt(report: OperationalValidationReport) -> None:
    from utils import atomic_json_write

    receipt_path = _live_smoke_receipt_path()
    atomic_json_write(
        receipt_path,
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "live_gateway_receipt": report.receipts["live_gateway"],
            "attachment_receipt": report.receipts["attachment"],
        },
    )


def _live_smoke_receipt_path() -> Path:
    raw = os.environ.get("MIHO_GOVERNANCE_LIVE_SMOKE_RECEIPT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    from miho_constants import get_miho_home

    return get_miho_home() / "governance_os" / "discord_live_smoke_receipt.json"


def _with_media_allow_dir(existing: str | None, path: Path) -> str:
    clean_path = str(path.expanduser().resolve())
    parts = [part for part in (existing or "").split(os.pathsep) if part]
    if clean_path not in parts:
        parts.append(clean_path)
    return os.pathsep.join(parts)
