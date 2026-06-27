"""Test receipt generation for Self-Harness promotion candidates."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from typing import Any

from .self_harness_autonomy import _required_tests

DEFAULT_TEST_TIMEOUT_SECONDS = 600
ReceiptRunner = Callable[[str], "tuple[int, str]"]


def generate_test_receipts(
    candidate: dict[str, Any],
    *,
    runner: ReceiptRunner | None = None,
) -> list[dict[str, Any]]:
    """Run each required test for a candidate and produce promotion receipts."""

    run = runner or _default_pytest_runner
    receipts: list[dict[str, Any]] = []
    for test_path in _required_tests(candidate):
        try:
            exit_code, evidence = run(test_path)
        except Exception as exc:  # a runner failure is a failed receipt, not a crash
            receipts.append(
                {
                    "name": test_path,
                    "status": "error",
                    "exit_code": 1,
                    "command": f"pytest {test_path}",
                    "evidence": f"runner error: {exc}",
                }
            )
            continue
        receipts.append(
            {
                "name": test_path,
                "status": "passed" if exit_code == 0 else "failed",
                "exit_code": int(exit_code),
                "command": f"pytest {test_path}",
                "evidence": str(evidence or "")[-800:] or f"pytest exit {exit_code}",
            }
        )
    return receipts


def _default_pytest_runner(test_path: str) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "pytest", test_path, "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        timeout=DEFAULT_TEST_TIMEOUT_SECONDS,
    )
    return proc.returncode, (proc.stdout + proc.stderr)
