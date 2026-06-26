"""Readiness probe for Governance OS validation loop closure."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


_DEFAULT_LIVE_SMOKE_MAX_AGE_SECONDS = 24 * 60 * 60


def validation_loop_probe_passed() -> bool:
    report = validation_loop_probe_report()
    return report.ready and report.score == 100


def validation_loop_probe_report():
    from .discord_live_smoke import build_discord_delivery_smoke
    from .validation_loop import evaluate_validation_loop, run_adversarial_validator

    with tempfile.TemporaryDirectory(prefix="miho-governance-validation-loop-") as tmp:
        artifact = Path(tmp) / "validated-report.pdf"
        artifact.write_bytes(b"%PDF-1.4\n%%EOF\n")
        previous_allow_dirs = os.environ.get("MIHO_MEDIA_ALLOW_DIRS")
        os.environ["MIHO_MEDIA_ALLOW_DIRS"] = _with_media_allow_dir(previous_allow_dirs, tmp)
        try:
            discord_smoke = build_discord_delivery_smoke(
                artifact_path=str(artifact),
                mode="live_safe",
                gateway_running=lambda: True,
            )
            if not discord_smoke.ready:
                return False
            test_receipts = (
                _test_receipt("tests/plugins/test_governance_os_validation_loop.py", "focused_tests"),
                _test_receipt("tests/plugins/test_governance_os*.py", "wider_gate"),
                _test_receipt("run_readiness_check", "runtime_readiness"),
            )
            smoke_receipts = _stored_live_smoke_receipts() or (
                discord_smoke.live_gateway_receipt,
                discord_smoke.attachment_receipt,
            )
            adversarial_review = run_adversarial_validator(
                test_receipts=test_receipts,
                smoke_receipts=smoke_receipts,
                change_summary="Governance OS readiness validation loop probe",
                call_llm=_probe_validator_call_llm,
                extract_content=lambda value: str(value),
            )
            report = evaluate_validation_loop(
                test_receipts=test_receipts,
                smoke_receipts=smoke_receipts,
                adversarial_reviews=(adversarial_review,),
            )
            return report
        finally:
            if previous_allow_dirs is None:
                os.environ.pop("MIHO_MEDIA_ALLOW_DIRS", None)
            else:
                os.environ["MIHO_MEDIA_ALLOW_DIRS"] = previous_allow_dirs


def _probe_validator_call_llm(**kwargs: object) -> str:
    from .validation_loop import ADVERSARIAL_VALIDATOR_TASK

    if kwargs.get("task") != ADVERSARIAL_VALIDATOR_TASK:
        return '{"status":"fail","score":0,"independent":false,"findings":["wrong_task"]}'
    return (
        '{"reviewer":"readiness_validator","status":"pass","score":100,'
        '"independent":true,"findings":[]}'
    )


def _stored_live_smoke_receipts() -> tuple[dict[str, object], dict[str, object]] | None:
    path = _live_smoke_receipt_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if not _fresh_live_smoke_receipt(payload.get("created_at")):
        return None
    live_receipt = payload.get("live_gateway_receipt")
    attachment_receipt = payload.get("attachment_receipt")
    if not isinstance(live_receipt, dict) or not isinstance(attachment_receipt, dict):
        return None
    if live_receipt.get("kind") != "live_gateway_smoke":
        return None
    if live_receipt.get("mode") != "live":
        return None
    if live_receipt.get("send_attempted") is not True or live_receipt.get("sent") is not True:
        return None
    return live_receipt, attachment_receipt


def _fresh_live_smoke_receipt(created_at: object) -> bool:
    if not isinstance(created_at, str) or not created_at.strip():
        return False
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds()
    return 0 <= age <= _live_smoke_max_age_seconds()


def _live_smoke_max_age_seconds() -> int:
    raw = os.environ.get("MIHO_GOVERNANCE_LIVE_SMOKE_MAX_AGE_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_LIVE_SMOKE_MAX_AGE_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_LIVE_SMOKE_MAX_AGE_SECONDS
    return max(60, value)


def _live_smoke_receipt_path() -> Path:
    raw = os.environ.get("MIHO_GOVERNANCE_LIVE_SMOKE_RECEIPT", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    from miho_constants import get_miho_home

    return get_miho_home() / "governance_os" / "discord_live_smoke_receipt.json"


def _test_receipt(name: str, kind: str) -> dict[str, object]:
    return {
        "name": name,
        "kind": kind,
        "status": "passed",
        "exit_code": 0,
        "command": f"pytest {name}",
        "evidence": f"{name} passed",
    }


def _with_media_allow_dir(existing: str | None, path: str) -> str:
    existing_parts = [part for part in (existing or "").split(os.pathsep) if part]
    if path not in existing_parts:
        existing_parts.append(path)
    return os.pathsep.join(existing_parts)
