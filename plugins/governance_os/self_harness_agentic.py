"""Agentic provenance helpers for Self-Harness candidates."""

from __future__ import annotations

from typing import Any

AGENTIC_PROPOSER_FIELD = "agentic_proposer_task"
EXPECTED_PROPOSER_TASK = "miho_self_harness_proposer"


def stamp_candidates(candidates: list[dict[str, Any]], *, proposer_task: str) -> list[dict[str, Any]]:
    return [{**candidate, AGENTIC_PROPOSER_FIELD: proposer_task} for candidate in candidates]


def is_agentic_candidate(candidate: dict[str, Any]) -> bool:
    return str(candidate.get(AGENTIC_PROPOSER_FIELD) or "") == EXPECTED_PROPOSER_TASK


def agentic_hold_record(candidate_id: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "reason": "llm_proposer_required",
        "missing_tests": [],
        "failed_tests": [],
        "contract_errors": ["Self-Harness activation requires LLM proposer provenance"],
    }
