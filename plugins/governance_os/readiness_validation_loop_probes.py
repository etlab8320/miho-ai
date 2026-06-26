"""Readiness probe for Governance OS validation loop closure."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def validation_loop_probe_passed() -> bool:
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
            smoke_receipts = (
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
            return report.ready and report.score == 100
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
