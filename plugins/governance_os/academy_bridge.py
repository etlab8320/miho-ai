"""Academy reviewer bridge into Governance OS outcome ledger."""

from __future__ import annotations

import logging
from typing import Any

from .ledger import OutcomeLedgerEntry, record_outcome


logger = logging.getLogger(__name__)

_PLAYBOOK_BY_TOOL = {
    "academy_hakjong_report_package": "academy_hakjong_report",
    "academy_practical_reco_package": "academy_practical_recommendation",
    "academy_practical_reco_all_candidates": "academy_practical_recommendation",
    "susi27_recommend_candidates": "academy_practical_recommendation",
    "susi27_score_calculate": "susi_score_calculation",
    "life_record_ingest_pdf": "life_record_ingest",
    "life_record_verify": "life_record_ingest",
}


def record_academy_review_outcome(tool_name: str, payload: dict[str, Any]) -> None:
    playbook_key = _PLAYBOOK_BY_TOOL.get(tool_name)
    if not playbook_key:
        return
    try:
        record_outcome(_entry(tool_name, playbook_key, payload))
    except Exception as exc:  # noqa: BLE001
        logger.debug("governance outcome record skipped: %s", exc, exc_info=True)


def _entry(tool_name: str, playbook_key: str, payload: dict[str, Any]) -> OutcomeLedgerEntry:
    reviewer = payload.get("reviewer") if isinstance(payload.get("reviewer"), dict) else {}
    return OutcomeLedgerEntry(
        request_id=_request_id(tool_name, payload),
        playbook_key=playbook_key,
        agent_chain=("academy_domain_agent", "result_reviewer", "ledger_writer"),
        tools_used=(tool_name,),
        review_status=str(reviewer.get("status") or _fallback_status(payload)),
        failures=_errors(payload),
        retry_tools=_retry_tools(tool_name, payload),
        artifact_paths=_artifact_paths(payload),
        promotion_candidates=(),
    )


def _request_id(tool_name: str, payload: dict[str, Any]) -> str:
    for key in ("request_id", "run_id", "manifest_path", "file_path", "review_path"):
        value = str(payload.get(key) or "").strip()
        if value:
            return f"{tool_name}:{value}"
    return tool_name


def _fallback_status(payload: dict[str, Any]) -> str:
    return "blocked" if payload.get("ok") is False else "unknown"


def _errors(payload: dict[str, Any]) -> tuple[str, ...]:
    errors = payload.get("errors")
    if not isinstance(errors, list):
        return ()
    return tuple(str(error) for error in errors if str(error).strip())


def _retry_tools(tool_name: str, payload: dict[str, Any]) -> tuple[str, ...]:
    reviewer = payload.get("reviewer") if isinstance(payload.get("reviewer"), dict) else {}
    status = str(reviewer.get("status") or "").strip()
    if status in {"blocked", "fail", "failed"} or payload.get("ok") is False:
        return (tool_name,)
    return ()


def _artifact_paths(payload: dict[str, Any]) -> tuple[str, ...]:
    paths: list[str] = []
    for key in ("file_path", "manifest_path", "review_path"):
        value = str(payload.get(key) or "").strip()
        if value:
            paths.append(value)
    return tuple(paths)
