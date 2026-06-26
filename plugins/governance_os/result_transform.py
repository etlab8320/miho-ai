"""Governance transform hook for self-reviewed tool results."""

from __future__ import annotations

import json
import logging
from typing import Any

from .ledger import OutcomeLedgerEntry, record_outcome
from .review import auxiliary_review_policy_for_playbook, evaluate_review_gate
from .versioning import load_runtime_registry


logger = logging.getLogger(__name__)

# 내부 재시도 지시(assistant_instruction)와 사용자 노출 문구(user_safe_message)를
# 명시적으로 분리한다. 사용자에게 보여도 안전한 평문만 user_safe_message로 둔다.
_USER_SAFE_RETRY_MESSAGE = "최종 결과 없음.\n필요한 입력: 검수 통과 산출물."

_SELF_REVIEWED_TOOL_PLAYBOOKS: dict[str, tuple[str, ...]] = {
    "academy_hakjong_report_package": ("academy_hakjong_report",),
    "academy_practical_reco_package": ("academy_practical_recommendation",),
    "academy_practical_reco_all_candidates": ("academy_practical_recommendation",),
    "susi27_recommend_candidates": ("academy_practical_recommendation",),
    "susi27_score_calculate": ("susi_score_calculation",),
    "life_record_ingest_pdf": ("life_record_ingest",),
    "life_record_verify": ("life_record_ingest",),
    "html_pdf_quality_gate": ("designed_pdf_artifact",),
    "media_delivery_contract": ("discord_attachment_delivery",),
}
_SUPPORT_RETRY_TOOLS = frozenset({"html_pdf_autocorrect", "vision_analyze"})


def governance_transform_tool_result(
    *,
    tool_name: str = "",
    result: Any = None,
    **context: Any,
) -> str | None:
    playbook_keys = _SELF_REVIEWED_TOOL_PLAYBOOKS.get(str(tool_name or ""))
    if not playbook_keys:
        return None
    if _is_tool_repair_contract(result):
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

    executor = _auto_retry_executor(
        tool_name=str(tool_name),
        failures=failures,
        context=context,
    )
    retry_result = _run_auto_retry_executor(
        registry=registry,
        executor=executor,
        context=context,
    )
    if retry_result is not None:
        return retry_result

    message = failures[0]["message_ko"] or (
        "후검증을 통과하지 못했습니다. 결과를 전달하지 말고 전용 도구를 다시 실행해야 합니다."
    )
    return json.dumps(
        {
            "success": False,
            "next_action": "retry_required",
            "delivery_status": "provisional" if _has_retry_needed(failures) else "blocked",
            "error": message,
            # 레이어 분리: 내부 전용 지시 vs 사용자 노출 안전 문구.
            "assistant_instruction": message,
            "user_safe_message": _USER_SAFE_RETRY_MESSAGE,
            "governance_review": {
                "status": _review_status(failures),
                "tool_name": str(tool_name),
                "failures": failures,
                "retry_tools": _retry_tools(failures),
                "retry_args": _retry_args(failures),
                "retry_instruction_ko": _retry_instruction_ko(failures),
            },
            "auto_retry_executor": executor,
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


def _is_tool_repair_contract(result: Any) -> bool:
    payload = _loads_object(result)
    if payload is None or payload.get("ok") is not False:
        return False
    if payload.get("retry_required") is True:
        return True
    if payload.get("final_response_allowed") is False:
        return True
    return str(payload.get("next_action") or "").strip() == "retry_required"


def _retry_tools(failures: list[dict[str, Any]]) -> list[str]:
    tools: list[str] = []
    for failure in failures:
        for tool in failure.get("retry_tools") or []:
            text = str(tool).strip()
            if text:
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


def _auto_retry_executor(
    *,
    tool_name: str,
    failures: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    retry_tools = _retry_tools(failures)
    retry_args = _retry_args(failures)
    original_args = context.get("args") if isinstance(context.get("args"), dict) else None
    if not retry_args and original_args and retry_tools == [tool_name]:
        retry_args = [original_args]
    return {
        "status": "required" if retry_tools else "not_available",
        "mode": "agentic_tool_loop",
        "tool_call_id": str(context.get("tool_call_id") or ""),
        "retry_tools": retry_tools,
        "retry_args": retry_args,
        "max_attempts": 2,
        "success_condition": (
            "retry tool result must pass Governance reviewer and final delivery agent"
        ),
        "user_visible_summary": _USER_SAFE_RETRY_MESSAGE,
    }


def _run_auto_retry_executor(
    *,
    registry: Any,
    executor: dict[str, Any],
    context: dict[str, Any],
) -> str | None:
    if executor.get("status") != "required":
        return None
    retry_tools = [str(item).strip() for item in executor.get("retry_tools") or [] if str(item).strip()]
    retry_args = [item for item in executor.get("retry_args") or [] if isinstance(item, dict)]
    if not retry_tools or not retry_args:
        return None

    attempts: list[dict[str, Any]] = []
    max_attempts = max(1, int(executor.get("max_attempts") or 1))
    prior_results: dict[str, dict[str, Any]] = {}
    for attempt in range(1, max_attempts + 1):
        for index, retry_tool in enumerate(retry_tools):
            args = _retry_args_with_prior_result(
                retry_tool=retry_tool,
                args=retry_args[min(index, len(retry_args) - 1)],
                prior_results=prior_results,
            )
            try:
                retry_result = _dispatch_retry_tool(retry_tool, args, context=context)
            except Exception as exc:
                attempts.append(
                    {
                        "attempt": attempt,
                        "tool_name": retry_tool,
                        "status": "fail",
                        "reason": f"retry_dispatch_error:{type(exc).__name__}",
                    }
                )
                continue
            prior_results[retry_tool] = _loads_object(retry_result) or {"raw": retry_result}
            status, reason = _review_retry_result(
                registry=registry,
                retry_tool=retry_tool,
                retry_result=retry_result,
                context=context,
            )
            attempts.append(
                {
                    "attempt": attempt,
                    "tool_name": retry_tool,
                    "status": status,
                    "reason": reason,
                }
            )
            if status == "pass" and index == len(retry_tools) - 1:
                executor["attempts"] = attempts
                return retry_result
    executor["attempts"] = attempts
    return None


def _retry_args_with_prior_result(
    *,
    retry_tool: str,
    args: dict[str, Any],
    prior_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    next_args = dict(args)
    if retry_tool == "html_pdf_quality_gate":
        if autocorrect := prior_results.get("html_pdf_autocorrect"):
            corrected = str(
                autocorrect.get("corrected_html_path")
                or autocorrect.get("html_path")
                or autocorrect.get("artifact_path")
                or ""
            ).strip()
            if corrected:
                next_args["html_path"] = corrected
        if not next_args.get("visual_review"):
            if vision_result := prior_results.get("vision_analyze"):
                next_args["visual_review"] = vision_result
    if retry_tool == "vision_analyze":
        quality = prior_results.get("html_pdf_quality_gate") or {}
        if not next_args.get("image_url"):
            contact_sheet = str(
                quality.get("contact_sheet_path")
                or (quality.get("pdf_quality_gate") or {}).get("contact_sheet")
                or ""
            ).strip()
            if contact_sheet:
                next_args["image_url"] = contact_sheet
        if not next_args.get("question"):
            prompt = str((quality.get("pdf_quality_gate") or {}).get("review_prompt") or "").strip()
            if prompt:
                next_args["question"] = prompt
    if retry_tool == "media_delivery_contract" and not next_args.get("artifact_path"):
        quality = prior_results.get("html_pdf_quality_gate") or {}
        artifact_path = str(
            quality.get("pdf_path")
            or quality.get("artifact_path")
            or (quality.get("pdf_quality_gate") or {}).get("pdf_path")
            or ""
        ).strip()
        if artifact_path:
            next_args["artifact_path"] = artifact_path
    return next_args


def _dispatch_retry_tool(
    retry_tool: str,
    args: dict[str, Any],
    *,
    context: dict[str, Any],
) -> str:
    from tools.registry import registry as tool_registry

    result = tool_registry.dispatch(
        retry_tool,
        args,
        task_id=str(context.get("task_id") or "") or None,
    )
    return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)


def _review_retry_result(
    *,
    registry: Any,
    retry_tool: str,
    retry_result: str,
    context: dict[str, Any],
) -> tuple[str, str]:
    if retry_tool in _SUPPORT_RETRY_TOOLS:
        payload = _loads_object(retry_result)
        if payload is not None and payload.get("success") is not False:
            return "pass", "support_tool_success"
        return "fail", "support_tool_failed"
    playbook_keys = _SELF_REVIEWED_TOOL_PLAYBOOKS.get(retry_tool, ())
    if not playbook_keys:
        return "fail", "retry_tool_not_self_reviewed"
    reasons: list[str] = []
    for playbook_key in playbook_keys:
        outcome = evaluate_review_gate(
            registry,
            playbook_key=playbook_key,
            tool_name=retry_tool,
            result=retry_result,
            auxiliary_review_policy=auxiliary_review_policy_for_playbook(playbook_key),
        )
        if outcome.status != "pass":
            reasons.append(outcome.reason)
            continue
        _record_transform_outcome(
            registry=registry,
            playbook_key=playbook_key,
            tool_name=retry_tool,
            result=retry_result,
            review_status="pass",
            failures=(),
            retry_tools=(),
            context={**context, "request_id": f"{_request_id(retry_tool, context)}:retry"},
        )
        return "pass", outcome.reason
    return "fail", ", ".join(reasons) or "retry_review_failed"
