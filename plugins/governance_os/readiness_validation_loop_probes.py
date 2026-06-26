"""Readiness probe for Governance OS validation loop closure."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def validation_loop_probe_passed() -> bool:
    from .discord_live_smoke import build_discord_delivery_smoke
    from .validation_loop import ADVERSARIAL_VALIDATOR_TASK, evaluate_validation_loop

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
            report = evaluate_validation_loop(
                test_receipts=(
                    _test_receipt("tests/plugins/test_governance_os_validation_loop.py", "focused_tests"),
                    _test_receipt("tests/plugins/test_governance_os*.py", "wider_gate"),
                    _test_receipt("run_readiness_check", "runtime_readiness"),
                ),
                smoke_receipts=(
                    discord_smoke.live_gateway_receipt,
                    discord_smoke.attachment_receipt,
                ),
                adversarial_reviews=(
                    {
                        "reviewer": "readiness_validator",
                        "task": ADVERSARIAL_VALIDATOR_TASK,
                        "status": "passed",
                        "score": 100,
                        "independent": True,
                        "findings": [],
                    },
                ),
            )
            return report.ready and report.score == 100
        finally:
            if previous_allow_dirs is None:
                os.environ.pop("MIHO_MEDIA_ALLOW_DIRS", None)
            else:
                os.environ["MIHO_MEDIA_ALLOW_DIRS"] = previous_allow_dirs


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
