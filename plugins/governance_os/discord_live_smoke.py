"""Discord delivery smoke receipts for Governance OS validation."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


DiscordSmokeMode = Literal["live_safe", "live"]
GatewayRunningFn = Callable[[], bool]
MediaContractFn = Callable[[dict[str, Any]], str]
SenderFn = Callable[[str, str], dict[str, Any]]


@dataclass(frozen=True)
class DiscordDeliverySmoke:
    ready: bool
    mode: DiscordSmokeMode
    preflight_receipt: dict[str, Any]
    live_gateway_receipt: dict[str, Any]
    attachment_receipt: dict[str, Any]
    failures: tuple[str, ...] = field(default_factory=tuple)


def build_discord_delivery_smoke(
    *,
    artifact_path: str,
    mode: DiscordSmokeMode = "live_safe",
    target: str = "",
    caption: str = "미호 Governance OS Discord delivery smoke.",
    gateway_running: GatewayRunningFn | None = None,
    media_contract: MediaContractFn | None = None,
    sender: SenderFn | None = None,
) -> DiscordDeliverySmoke:
    failures: list[str] = []
    gateway_ok = _gateway_running(gateway_running)
    if not gateway_ok:
        failures.append("gateway_not_running")

    media_payload = _run_media_contract(
        artifact_path=artifact_path,
        caption=caption,
        media_contract=media_contract,
    )
    if media_payload.get("success") is not True:
        failures.append("media_contract_failed")

    deliverable_path = str(media_payload.get("artifact_path") or artifact_path).strip()
    media_tag = str(media_payload.get("media_tag") or "").strip()
    delivery_text = str(media_payload.get("delivery_text") or f"{caption}\n{media_tag}").strip()
    artifact_ok = _artifact_ok(deliverable_path, media_tag)
    if not artifact_ok:
        failures.append("artifact_not_deliverable")

    send_attempted = False
    sent = False
    if mode == "live":
        send_attempted = True
        if not target:
            failures.append("discord_target_missing")
        elif gateway_ok and artifact_ok and sender is not None:
            sent = _send_discord_smoke(sender, target=target, message=delivery_text)
            if not sent:
                failures.append("discord_send_failed")
        else:
            failures.append("discord_sender_missing")

    ready = not failures
    status = "passed" if ready else "failed"
    evidence = _evidence(
        mode=mode,
        gateway_ok=gateway_ok,
        artifact_ok=artifact_ok,
        send_attempted=send_attempted,
        sent=sent,
    )
    return DiscordDeliverySmoke(
        ready=ready,
        mode=mode,
        failures=tuple(failures),
        preflight_receipt={
            "name": "discord_delivery",
            "status": status,
            "exit_code": 0 if ready else 1,
            "command": "governance discord delivery smoke",
            "evidence": evidence,
        },
        live_gateway_receipt={
            "name": "discord live gateway smoke",
            "kind": "live_gateway_smoke",
            "status": status,
            "mode": mode,
            "send_attempted": send_attempted,
            "sent": sent,
            "evidence": evidence,
        },
        attachment_receipt={
            "name": "discord attachment artifact smoke",
            "kind": "attachment_artifact_smoke",
            "status": status,
            "artifact_path": deliverable_path,
            "media_tag": media_tag,
            "evidence": evidence,
        },
    )


def _gateway_running(gateway_running: GatewayRunningFn | None) -> bool:
    if gateway_running is not None:
        return bool(gateway_running())
    try:
        from gateway.status import is_gateway_running

        return bool(is_gateway_running())
    except Exception:
        return False


def _run_media_contract(
    *,
    artifact_path: str,
    caption: str,
    media_contract: MediaContractFn | None,
) -> dict[str, Any]:
    runner = media_contract
    if runner is None:
        from tools.media_delivery_contract_tool import media_delivery_contract_tool

        runner = media_delivery_contract_tool
    try:
        payload = json.loads(runner({"artifact_path": artifact_path, "caption": caption}))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"success": False}
    return payload if isinstance(payload, dict) else {"success": False}


def _artifact_ok(artifact_path: str, media_tag: str) -> bool:
    if not artifact_path or not media_tag.startswith("MEDIA:"):
        return False
    try:
        path = Path(artifact_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        return False
    return path.is_file() and artifact_path in media_tag


def _send_discord_smoke(sender: SenderFn, *, target: str, message: str) -> bool:
    try:
        result = sender(target, message)
    except Exception:
        return False
    if not isinstance(result, dict):
        return False
    if result.get("success") is True:
        return True
    return str(result.get("status") or "").strip() in {"passed", "sent", "success"}


def _evidence(
    *,
    mode: DiscordSmokeMode,
    gateway_ok: bool,
    artifact_ok: bool,
    send_attempted: bool,
    sent: bool,
) -> str:
    return (
        f"mode={mode}; gateway_running={gateway_ok}; "
        f"artifact_deliverable={artifact_ok}; send_attempted={send_attempted}; sent={sent}"
    )
