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

import hashlib
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from .self_harness import build_evidence_bundle, build_shadow_candidates
from .self_harness_agentic import agentic_hold_record, is_agentic_candidate, stamp_candidates
from .self_harness_autonomy import (
    activate_autonomous_candidate,
    decide_autonomous_activation,
    rollback_on_regression,
)
from .self_harness_cron import (
    CRON_JOB_NAME,
    DEFAULT_CRON_SCHEDULE,
    _AUTOPILOT_SCRIPT_NAME,
    _install_autopilot_script,
    register_self_harness_cron,
)
from .self_harness_receipts import (
    DEFAULT_TEST_TIMEOUT_SECONDS,
    ReceiptRunner,
    _default_pytest_runner,
    generate_test_receipts,
)

logger = logging.getLogger(__name__)

WEAKNESS_MINER_TASK = "miho_self_harness_weakness_miner"
PROPOSER_TASK = "miho_self_harness_proposer"
DEFAULT_EVENT_LIMIT = 200

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

LlmCaller = Callable[..., Any]
ContentExtractor = Callable[[Any], str]


def run_self_harness_autopilot(
    *,
    events: Iterable[dict[str, Any]] | None = None,
    event_limit: int = DEFAULT_EVENT_LIMIT,
    min_recurrence: int = 2,
    registry: Any = None,
    base_dir: Any = None,
    receipt_runner: ReceiptRunner | None = None,
    smoke_runner: ReceiptRunner | None = None,
    call_llm: LlmCaller | None = None,
    extract_content: ContentExtractor | None = None,
    max_activations: int | None = 1,
) -> dict[str, Any]:
    """Run one full autonomous Self-Harness cycle and return a summary.

    The loop is deterministic and side-effecting only through the injected
    ``receipt_runner`` (defaults to a real pytest subprocess) and the governance
    registry activation/rollback functions.
    """

    runner = receipt_runner or _default_pytest_runner
    smoke = smoke_runner or runner

    event_items = list(_fetch_recent_events(event_limit) if events is None else events)
    bundle = _mine_evidence_bundle(
        event_items,
        min_recurrence=min_recurrence,
        call_llm=call_llm,
        extract_content=extract_content,
    )
    candidates = _propose_shadow_candidates(
        bundle,
        call_llm=call_llm,
        extract_content=extract_content,
    )

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


def _mine_evidence_bundle(
    events: list[dict[str, Any]],
    *,
    min_recurrence: int,
    call_llm: LlmCaller | None,
    extract_content: ContentExtractor | None,
) -> dict[str, Any]:
    deterministic = build_evidence_bundle(events, min_recurrence=min_recurrence)
    refined = _call_self_harness_json(
        WEAKNESS_MINER_TASK,
        payload={
            "events": events[-DEFAULT_EVENT_LIMIT:],
            "deterministic_bundle": deterministic,
            "contract": "Return a miho-self-harness/evidence-bundle/v1 JSON object only.",
        },
        call_llm=call_llm,
        extract_content=extract_content,
    )
    if isinstance(refined, dict) and _valid_evidence_bundle(refined):
        return refined
    return deterministic


def _propose_shadow_candidates(
    bundle: dict[str, Any],
    *,
    call_llm: LlmCaller | None,
    extract_content: ContentExtractor | None,
) -> list[dict[str, Any]]:
    deterministic = build_shadow_candidates(bundle)
    proposal_payload = {
        "evidence_bundle": bundle,
        "deterministic_candidates": deterministic,
        "contract": (
            "Return JSON with candidates: [miho-self-harness/shadow-candidate/v1]. "
            "Every candidate must start auto_promote_allowed=false and include rollback."
        ),
    }
    refined = _call_self_harness_json(
        PROPOSER_TASK,
        payload=proposal_payload,
        call_llm=call_llm,
        extract_content=extract_content,
    )
    candidates = _candidate_list_from_payload(refined)
    if candidates:
        return stamp_candidates(
            candidates,
            proposer_task=PROPOSER_TASK,
            prompt_sha256=_stable_payload_digest(proposal_payload),
        )
    return stamp_candidates(deterministic, proposer_task="")


def _call_self_harness_json(
    task: str,
    *,
    payload: dict[str, Any],
    call_llm: LlmCaller | None,
    extract_content: ContentExtractor | None,
) -> dict[str, Any] | list[Any] | None:
    try:
        if call_llm is None or extract_content is None:
            from agent.auxiliary_client import call_llm as default_call_llm
            from agent.auxiliary_client import extract_content_or_reasoning

            call_llm = call_llm or default_call_llm
            extract_content = extract_content or extract_content_or_reasoning
        response = call_llm(
            task=task,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "너는 미호 Self-Harness 에이전트다. 입력 JSON만 근거로 삼고, "
                        "기존 런타임을 직접 바꾸지 않는 검증 가능한 JSON만 출력한다."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.0,
            max_tokens=1800,
            timeout=60,
        )
        parsed = _parse_json_payload(str(extract_content(response) or ""))
    except Exception as exc:
        logger.info("self-harness LLM task %s unavailable: %s", task, exc)
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def _parse_json_payload(text: str) -> Any:
    body = str(text or "").strip()
    if body.startswith("```"):
        lines = body.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        body = "\n".join(lines).strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        starts = [index for index in (body.find("{"), body.find("[")) if index >= 0]
        if not starts:
            raise
        start = min(starts)
        end = max(body.rfind("}"), body.rfind("]"))
        if end <= start:
            raise
        return json.loads(body[start : end + 1])


def _valid_evidence_bundle(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("schema_version") == "miho-self-harness/evidence-bundle/v1"
        and isinstance(value.get("patterns"), list)
    )


def _candidate_list_from_payload(value: Any) -> list[dict[str, Any]]:
    raw = value.get("candidates") if isinstance(value, dict) else value
    if not isinstance(raw, list):
        return []
    candidates = [item for item in raw if isinstance(item, dict) and _valid_shadow_candidate(item)]
    return candidates


def _valid_shadow_candidate(candidate: dict[str, Any]) -> bool:
    validation = candidate.get("validation")
    source = candidate.get("source_pattern")
    return (
        candidate.get("schema_version") == "miho-self-harness/shadow-candidate/v1"
        and candidate.get("status") == "shadow_candidate"
        and candidate.get("auto_promote_allowed") is False
        and bool(str(candidate.get("target_surface") or "").strip())
        and bool(str(candidate.get("rollback") or "").strip())
        and isinstance(validation, dict)
        and isinstance(validation.get("required_tests"), list | tuple)
        and isinstance(source, dict)
    )


def _process_candidate(
    candidate: dict[str, Any],
    *,
    runner: ReceiptRunner,
    smoke: ReceiptRunner,
    registry: Any,
    base_dir: Any,
) -> dict[str, Any]:
    candidate_id = str(candidate.get("id") or "")
    if not is_agentic_candidate(candidate):
        return {"bucket": "held", "record": agentic_hold_record(candidate_id)}
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


def _stable_payload_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
