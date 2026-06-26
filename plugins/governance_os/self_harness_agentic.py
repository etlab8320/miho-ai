"""Agentic provenance helpers for Self-Harness candidates."""

from __future__ import annotations

from typing import Any

AGENTIC_PROPOSER_FIELD = "agentic_proposer_task"
AGENTIC_PROPOSER_RECEIPT_FIELD = "agentic_proposer_receipt"
EXPECTED_PROPOSER_TASK = "miho_self_harness_proposer"


def stamp_candidates(
    candidates: list[dict[str, Any]],
    *,
    proposer_task: str,
    prompt_sha256: str = "",
) -> list[dict[str, Any]]:
    receipt = _proposer_receipt(proposer_task=proposer_task, prompt_sha256=prompt_sha256)
    return [
        {
            **candidate,
            AGENTIC_PROPOSER_FIELD: proposer_task,
            AGENTIC_PROPOSER_RECEIPT_FIELD: receipt,
        }
        for candidate in candidates
    ]


def is_agentic_candidate(candidate: dict[str, Any]) -> bool:
    receipt = candidate.get(AGENTIC_PROPOSER_RECEIPT_FIELD)
    return (
        str(candidate.get(AGENTIC_PROPOSER_FIELD) or "") == EXPECTED_PROPOSER_TASK
        and isinstance(receipt, dict)
        and str(receipt.get("task") or "") == EXPECTED_PROPOSER_TASK
        and str(receipt.get("transport") or "") == "auxiliary_llm"
        and bool(str(receipt.get("prompt_sha256") or "").strip())
    )


def agentic_hold_record(candidate_id: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "reason": "llm_proposer_required",
        "missing_tests": [],
        "failed_tests": [],
        "contract_errors": ["Self-Harness activation requires LLM proposer execution receipt"],
    }


def _proposer_receipt(*, proposer_task: str, prompt_sha256: str) -> dict[str, Any]:
    if proposer_task != EXPECTED_PROPOSER_TASK:
        return {}
    return {
        "task": proposer_task,
        "transport": "auxiliary_llm",
        "prompt_sha256": prompt_sha256,
    }
