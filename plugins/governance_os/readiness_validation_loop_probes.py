"""Readiness probe for Governance OS validation loop closure."""

from __future__ import annotations

import tempfile
from pathlib import Path


def validation_loop_probe_passed() -> bool:
    from .validation_loop import ADVERSARIAL_VALIDATOR_TASK, evaluate_validation_loop

    with tempfile.TemporaryDirectory(prefix="miho-governance-validation-loop-") as tmp:
        artifact = Path(tmp) / "validated-report.pdf"
        artifact.write_bytes(b"%PDF-1.4\n%%EOF\n")
        report = evaluate_validation_loop(
            test_receipts=(
                _test_receipt("tests/plugins/test_governance_os_validation_loop.py", "focused_tests"),
                _test_receipt("tests/plugins/test_governance_os*.py", "wider_gate"),
                _test_receipt("run_readiness_check", "runtime_readiness"),
            ),
            smoke_receipts=(
                {
                    "name": "gateway live-safe smoke",
                    "kind": "live_gateway_smoke",
                    "status": "passed",
                    "mode": "live_safe",
                    "evidence": "readiness exercised gateway hook path without sending a Discord message",
                },
                {
                    "name": "attachment artifact smoke",
                    "kind": "attachment_artifact_smoke",
                    "status": "passed",
                    "artifact_path": str(artifact),
                    "media_tag": f"MEDIA:`{artifact}`",
                    "evidence": "local artifact exists and is represented by a MEDIA tag",
                },
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


def _test_receipt(name: str, kind: str) -> dict[str, object]:
    return {
        "name": name,
        "kind": kind,
        "status": "passed",
        "exit_code": 0,
        "command": f"pytest {name}",
        "evidence": f"{name} passed",
    }
