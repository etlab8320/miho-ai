"""Autonomous Self-Harness improvement loop for Miho Governance OS.

Wires the previously disconnected pieces into one unattended loop:

    evidence mining  ->  shadow candidates  ->  test receipts (real pytest)
        ->  autonomous activation (real registry write)
        ->  post-activation regression smoke  ->  rollback on regression

This is what makes the Self-Harness a *real* auto-improvement loop rather than a
proposal collector: ``run_self_harness_autopilot`` actually generates test
receipts, activates validated candidates, and rolls back any activation whose
post-activation smoke tests regress. ``register_self_harness_cron`` schedules it
to run unattended via the cron scheduler.

Safety invariants kept intact:
- ``auto_promote_allowed`` must start false (enforced by the activation contract).
- Unsafe candidate text (prompt-injection / secret-path patterns) is skipped.
- Every activation snapshots the registry first and rolls back on regression.
- One failing candidate never aborts the whole loop.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .self_harness import build_evidence_bundle, build_shadow_candidates
from .self_harness_autonomy import (
    _required_tests,
    activate_autonomous_candidate,
    decide_autonomous_activation,
    rollback_on_regression,
)

logger = logging.getLogger(__name__)

CRON_JOB_NAME = "governance_self_harness_autopilot"
DEFAULT_CRON_SCHEDULE = "0 4 * * *"  # daily 04:00 server time
DEFAULT_EVENT_LIMIT = 200
DEFAULT_TEST_TIMEOUT_SECONDS = 600

# Defense-in-depth: never activate a candidate whose mined text smells like a
# prompt-injection or secret-exfiltration payload, even if its tests pass.
_UNSAFE_CANDIDATE_PATTERNS = (
    "ignore previous instructions",
    "disregard your instructions",
    "system prompt override",
    "do not tell the user",
    "authorized_keys",
    "~/.ssh",
    ".env",
    "secret",
    "password",
)

# Type alias: a receipt runner maps a pytest target to (exit_code, evidence_tail).
ReceiptRunner = Callable[[str], "tuple[int, str]"]


def run_self_harness_autopilot(
    *,
    events: Iterable[dict[str, Any]] | None = None,
    event_limit: int = DEFAULT_EVENT_LIMIT,
    min_recurrence: int = 2,
    registry: Any = None,
    base_dir: Any = None,
    receipt_runner: ReceiptRunner | None = None,
    smoke_runner: ReceiptRunner | None = None,
    max_activations: int | None = 1,
) -> dict[str, Any]:
    """Run one full autonomous Self-Harness cycle and return a summary.

    The loop is deterministic and side-effecting only through the injected
    ``receipt_runner`` (defaults to a real pytest subprocess) and the governance
    registry activation/rollback functions.
    """

    runner = receipt_runner or _default_pytest_runner
    smoke = smoke_runner or runner

    if events is None:
        events = _fetch_recent_events(event_limit)
    bundle = build_evidence_bundle(events, min_recurrence=min_recurrence)
    candidates = build_shadow_candidates(bundle)

    activated: list[dict[str, Any]] = []
    held: list[dict[str, Any]] = []
    rolled_back: list[dict[str, Any]] = []
    skipped_unsafe: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for candidate in candidates:
        candidate_id = str(candidate.get("id") or "")
        if _is_unsafe_candidate(candidate):
            skipped_unsafe.append({"candidate_id": candidate_id, "reason": "unsafe_candidate_text"})
            continue
        if max_activations is not None and len(activated) >= max_activations:
            held.append({"candidate_id": candidate_id, "reason": "max_activations_reached"})
            continue
        try:
            outcome = _process_candidate(
                candidate,
                runner=runner,
                smoke=smoke,
                registry=registry,
                base_dir=base_dir,
            )
        except Exception as exc:  # one bad candidate must not abort the loop
            logger.warning("self-harness candidate %s failed: %s", candidate_id, exc, exc_info=True)
            errors.append({"candidate_id": candidate_id, "error": str(exc)})
            continue
        bucket = outcome["bucket"]
        if bucket == "activated":
            activated.append(outcome["record"])
        elif bucket == "rolled_back":
            rolled_back.append(outcome["record"])
        else:
            held.append(outcome["record"])

    return {
        "schema_version": "miho-self-harness/autopilot-run/v1",
        "candidate_count": len(candidates),
        "activated": activated,
        "rolled_back": rolled_back,
        "held": held,
        "skipped_unsafe": skipped_unsafe,
        "errors": errors,
    }


def _process_candidate(
    candidate: dict[str, Any],
    *,
    runner: ReceiptRunner,
    smoke: ReceiptRunner,
    registry: Any,
    base_dir: Any,
) -> dict[str, Any]:
    candidate_id = str(candidate.get("id") or "")
    receipts = generate_test_receipts(candidate, runner=runner)
    decision = decide_autonomous_activation(candidate, test_receipts=receipts)
    if decision["action"] != "activate":
        return {
            "bucket": "held",
            "record": {
                "candidate_id": candidate_id,
                "reason": decision["reason"],
                "missing_tests": decision["missing_tests"],
                "failed_tests": decision["failed_tests"],
                "contract_errors": decision["contract_errors"],
            },
        }

    activation = activate_autonomous_candidate(
        candidate,
        test_receipts=receipts,
        registry=registry,
        base_dir=base_dir,
    )

    # Post-activation regression smoke: re-run the same guard tests against the
    # now-active registry. Any regression triggers an automatic rollback.
    regression_receipts = generate_test_receipts(candidate, runner=smoke)
    rollback = rollback_on_regression(
        activation,
        regression_receipts=regression_receipts,
        base_dir=base_dir,
    )
    if rollback is not None:
        return {
            "bucket": "rolled_back",
            "record": {
                "candidate_id": candidate_id,
                "target_surface": str(candidate.get("target_surface") or ""),
                "rollback_snapshot_id": activation.rollback_snapshot_id,
                "reason": "post_activation_regression",
            },
        }
    return {
        "bucket": "activated",
        "record": {
            "candidate_id": candidate_id,
            "target_surface": str(candidate.get("target_surface") or ""),
            "snapshot_id": activation.snapshot_id,
            "rollback_snapshot_id": activation.rollback_snapshot_id,
            "event_id": activation.event_id,
        },
    }


def generate_test_receipts(
    candidate: dict[str, Any],
    *,
    runner: ReceiptRunner | None = None,
) -> list[dict[str, Any]]:
    """Run each required test for a candidate and produce promotion receipts.

    ``runner`` maps a pytest target to ``(exit_code, evidence_tail)``. The default
    spawns a real pytest subprocess; tests inject a fake runner.
    """

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


def register_self_harness_cron(
    *,
    schedule: str = DEFAULT_CRON_SCHEDULE,
    script_path: str = "",
) -> dict[str, Any] | None:
    """Register (idempotently) the unattended Self-Harness autopilot cron job.

    Uses a ``no_agent`` script job so the loop runs deterministically on schedule
    without invoking an LLM. The runner is installed into ``~/.miho/scripts`` (the
    only location cron's path guard trusts) and registered by basename, so the
    cron scheduler actually executes it. Returns the created job, or None if it
    already exists.
    """

    from cron.jobs import create_job, list_jobs

    for job in list_jobs(include_disabled=True):
        if str(job.get("name") or "") == CRON_JOB_NAME:
            return None

    script_arg = script_path or _install_autopilot_script()
    return create_job(
        prompt=None,
        schedule=schedule,
        name=CRON_JOB_NAME,
        script=script_arg,
        no_agent=True,
        deliver="local",
    )


_AUTOPILOT_SCRIPT_NAME = "governance_self_harness_autopilot.py"


def _install_autopilot_script() -> str:
    """Write the autopilot runner into ~/.miho/scripts and return its basename.

    cron's path guard only allows scripts resolved under ~/.miho/scripts, and a
    copied file could not locate the repo via __file__. So we generate a thin shim
    with the current repo root baked in, then register it by relative name.
    """

    from pathlib import Path

    from miho_constants import get_miho_home

    repo_root = Path(__file__).resolve().parents[2]
    scripts_dir = get_miho_home() / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    destination = scripts_dir / _AUTOPILOT_SCRIPT_NAME
    shim = (
        "#!/usr/bin/env python3\n"
        "# Auto-generated by governance_os.self_harness_loop. Do not edit by hand.\n"
        "import json\n"
        "import sys\n"
        f"sys.path.insert(0, {str(repo_root)!r})\n"
        "from plugins.governance_os.self_harness_loop import run_self_harness_autopilot\n"
        "summary = run_self_harness_autopilot()\n"
        "print(json.dumps(summary, ensure_ascii=False, indent=2))\n"
        "sys.exit(1 if summary.get('errors') else 0)\n"
    )
    destination.write_text(shim, encoding="utf-8")
    return _AUTOPILOT_SCRIPT_NAME


def _fetch_recent_events(event_limit: int) -> list[dict[str, Any]]:
    try:
        from agent import evolution

        return list(evolution.list_events(limit=max(1, int(event_limit))))
    except Exception as exc:
        logger.warning("self-harness could not load events: %s", exc)
        return []


def _is_unsafe_candidate(candidate: Mapping[str, Any]) -> bool:
    source = candidate.get("source_pattern")
    failure = ""
    evidence_blob = ""
    if isinstance(source, Mapping):
        failure = str(source.get("failure_signature") or "")
        evidence_blob = " ".join(str(item) for item in source.get("evidence") or ())
    blob = " ".join(
        str(part)
        for part in (
            candidate.get("change_intent"),
            candidate.get("target_surface"),
            failure,
            evidence_blob,
        )
    ).casefold()
    return any(pattern in blob for pattern in _UNSAFE_CANDIDATE_PATTERNS)


def _default_pytest_runner(test_path: str) -> tuple[int, str]:
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "pytest", test_path, "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        timeout=DEFAULT_TEST_TIMEOUT_SECONDS,
    )
    return proc.returncode, (proc.stdout + proc.stderr)
