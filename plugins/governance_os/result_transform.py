"""Governance transform hook for self-reviewed tool results."""

from __future__ import annotations

import json
import logging
from typing import Any

from .ledger import OutcomeLedgerEntry, record_outcome
from .review import auxiliary_review_policy_for_playbook, evaluate_review_gate
from .versioning import load_runtime_registry


logger = logging.getLogger(__name__)

_SELF_REVIEWED_TOOL_PLAYBOOKS: dict[str, tuple[str, ...]] = {
    "academy_hakjong_report_package": ("academy_hakjong_report",),
    "academy_practical_reco_package": ("academy_practical_recommendation",),
    "academy_practical_reco_all_candidates": ("academy_practical_recommendation",),
    "susi27_recommend_candidates": ("academy_practical_recommendation",),
    "susi27_score_calculate": ("susi_score_calculation",),
    "life_record_ingest_pdf": ("life_record_ingest",),
    "life_record_verify": ("life_record_ingest",),
    "media_delivery_contract": ("discord_attachment_delivery",),
}


def governance_transform_tool_result(
    *,
    tool_name: str = "",
    result: Any = None,
    **context: Any,
) -> str | None:
    playbook_keys = _SELF_REVIEWED_TOOL_PLAYBOOKS.get(str(tool_name or ""))
    if not playbook_keys:
        return None

    registry = load_runtime_registry()
    failures: list[dict[str, Any]] = []
    for playbook_key in playbook_keys:
        outcome = evaluate_review_gate(
            registry,
            playbook_key=playbook_key,
            tool_name=str(tool_name),
            result=result,
            auxiliary_review_policy=auxiliary_review_policy_for_playbook(playbook_key),
        )
        if outcome.status == "pass":
            _record_transform_outcome(
                registry=registry,
                playbook_key=playbook_key,
                tool_name=str(tool_name),
                result=result,
                review_status="pass",
                failures=(),
                retry_tools=(),
                context=context,
            )
            return None
        _record_transform_outcome(
            registry=registry,
            playbook_key=playbook_key,
            tool_name=str(tool_name),
            result=result,
            review_status=outcome.status,
            failures=(outcome.reason,),
            retry_tools=outcome.retry_tools,
            context=context,
        )
        failures.append(
            {
                "playbook_key": playbook_key,
                "status": outcome.status,
                "reason": outcome.reason,
                "message_ko": outcome.message_ko,
                "retry_tools": list(outcome.retry_tools),
                "retry_args": list(outcome.retry_args),
                "retry_instruction_ko": outcome.retry_instruction_ko,
            }
        )

    message = failures[0]["message_ko"] or (
        "후검증을 통과하지 못했습니다. 결과를 전달하지 말고 전용 도구를 다시 실행해야 합니다."
    )
    return json.dumps(
        {
            "success": False,
            "next_action": "retry_required",
            "delivery_status": "provisional" if _has_retry_needed(failures) else "blocked",
            "error": message,
            "governance_review": {
                "status": _review_status(failures),
                "tool_name": str(tool_name),
                "failures": failures,
                "retry_tools": _retry_tools(failures),
                "retry_args": _retry_args(failures),
                "retry_instruction_ko": _retry_instruction_ko(failures),
            },
        },
        ensure_ascii=False,
    )


def _record_transform_outcome(
    *,
    registry: Any,
    playbook_key: str,
    tool_name: str,
    result: Any,
    review_status: str,
    failures: tuple[str, ...],
    retry_tools: tuple[str, ...],
    context: dict[str, Any],
) -> None:
    if context.get("governance_skip_ledger"):
        return
    try:
        playbook = registry.get_playbook(playbook_key)
        entry = OutcomeLedgerEntry(
            request_id=_request_id(tool_name, context),
            playbook_key=playbook_key,
            agent_chain=playbook.agent_chain,
            tools_used=(tool_name,),
            duration_ms=_duration_ms(context.get("duration_ms")),
            review_status=review_status,
            failures=failures,
            retry_tools=retry_tools,
            artifact_paths=_artifact_paths(result),
        )
        recorder = context.get("governance_ledger_recorder")
        if callable(recorder):
            recorder(entry)
        else:
            record_outcome(entry)
    except Exception as exc:
        logger.warning("governance transform outcome record failed: %s", exc, exc_info=True)


def _request_id(tool_name: str, context: dict[str, Any]) -> str:
    for key in ("request_id", "tool_call_id", "session_id", "task_id"):
        value = str(context.get(key) or "").strip()
        if value:
            return value
    return f"tool:{tool_name or 'unknown'}"


def _duration_ms(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _artifact_paths(result: Any) -> tuple[str, ...]:
    payload = _loads_object(result)
    if payload is None:
        return ()
    paths: list[str] = []
    for key in ("artifact_path", "file_path", "document_path", "path"):
        _append_path(paths, payload.get(key))
    for key in ("artifact_paths", "file_paths", "document_paths"):
        value = payload.get(key)
        if isinstance(value, (list, tuple, set)):
            for item in value:
                _append_path(paths, item)
    return tuple(paths)


def _append_path(paths: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in paths:
        paths.append(text)


def _loads_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _retry_tools(failures: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    for failure in failures:
        for tool in failure.get("retry_tools") or []:
            text = str(tool).strip()
            if text and text not in tools:
                tools.append(text)
    return tools


def _retry_args(failures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for failure in failures:
        for item in failure.get("retry_args") or []:
            if isinstance(item, dict):
                items.append(item)
    return items


def _has_retry_needed(failures: list[dict[str, Any]]) -> bool:
    return any(failure.get("status") == "retry_needed" for failure in failures)


def _review_status(failures: list[dict[str, Any]]) -> str:
    return "retry_needed" if _has_retry_needed(failures) else "fail"


def _retry_instruction_ko(failures: list[dict[str, Any]]) -> str:
    for failure in failures:
        instruction = str(failure.get("retry_instruction_ko") or "").strip()
        if instruction:
            return instruction
    return "결과를 전달하지 말고 같은 작업을 전용 도구로 다시 실행해 주세요."
