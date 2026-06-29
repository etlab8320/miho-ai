"""Finish-reason detection and truncated-response recovery."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class LengthRecoveryResult:
    action: str
    finish_reason: str
    length_continue_retries: int
    truncated_tool_call_retries: int
    truncated_response_parts: List[str]
    restart_with_length_continuation: bool
    return_value: Dict[str, Any] | None = None


def handle_finish_reason_and_length(
    *,
    agent: Any,
    response: Any,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    effective_task_id: str,
    api_call_count: int,
    length_continue_retries: int,
    truncated_tool_call_retries: int,
    truncated_response_parts: List[str],
) -> LengthRecoveryResult:
    """Resolve finish_reason and handle max-output truncation paths."""

    finish_reason = _finish_reason(agent, response, messages)
    if finish_reason != "length":
        return LengthRecoveryResult(
            action="proceed",
            finish_reason=finish_reason,
            length_continue_retries=length_continue_retries,
            truncated_tool_call_retries=truncated_tool_call_retries,
            truncated_response_parts=truncated_response_parts,
            restart_with_length_continuation=False,
        )

    agent._vprint(
        f"{agent.log_prefix}⚠️  Response truncated (finish_reason='length') - "
        "model hit max output tokens",
        force=True,
    )
    trunc_msg = _normalize_truncated_message(agent, response)
    trunc_content = getattr(trunc_msg, "content", None) if trunc_msg else None
    trunc_has_tool_calls = bool(getattr(trunc_msg, "tool_calls", None)) if trunc_msg else False

    exhausted = _thinking_exhausted(agent, trunc_content, trunc_has_tool_calls)
    if exhausted:
        return _thinking_exhausted_result(
            agent=agent,
            messages=messages,
            conversation_history=conversation_history,
            effective_task_id=effective_task_id,
            api_call_count=api_call_count,
            finish_reason=finish_reason,
            length_continue_retries=length_continue_retries,
            truncated_tool_call_retries=truncated_tool_call_retries,
            truncated_response_parts=truncated_response_parts,
        )

    if agent.api_mode in {"chat_completions", "bedrock_converse", "anthropic_messages", "codex_responses"}:
        if trunc_msg is not None and not trunc_has_tool_calls:
            return _text_continuation_result(
                agent=agent,
                messages=messages,
                conversation_history=conversation_history,
                effective_task_id=effective_task_id,
                api_call_count=api_call_count,
                finish_reason=finish_reason,
                length_continue_retries=length_continue_retries,
                truncated_tool_call_retries=truncated_tool_call_retries,
                truncated_response_parts=truncated_response_parts,
                assistant_message=trunc_msg,
            )
        if trunc_msg is not None and trunc_has_tool_calls:
            return _truncated_tool_call_result(
                agent=agent,
                messages=messages,
                conversation_history=conversation_history,
                effective_task_id=effective_task_id,
                api_call_count=api_call_count,
                finish_reason=finish_reason,
                length_continue_retries=length_continue_retries,
                truncated_tool_call_retries=truncated_tool_call_retries,
                truncated_response_parts=truncated_response_parts,
            )

    return _rollback_or_fail_first_truncation(
        agent=agent,
        messages=messages,
        conversation_history=conversation_history,
        api_call_count=api_call_count,
        finish_reason=finish_reason,
        length_continue_retries=length_continue_retries,
        truncated_tool_call_retries=truncated_tool_call_retries,
        truncated_response_parts=truncated_response_parts,
        effective_task_id=effective_task_id,
    )


def _finish_reason(agent: Any, response: Any, messages: List[Dict[str, Any]]) -> str:
    if agent.api_mode == "codex_responses":
        status = getattr(response, "status", None)
        details = getattr(response, "incomplete_details", None)
        reason = details.get("reason") if isinstance(details, dict) else getattr(details, "reason", None)
        return "length" if status == "incomplete" and reason in {"max_output_tokens", "length"} else "stop"
    if agent.api_mode == "anthropic_messages":
        return agent._get_transport().map_finish_reason(response.stop_reason)
    if agent.api_mode == "bedrock_converse":
        return agent._get_transport().normalize_response(response).finish_reason

    result = agent._get_transport().normalize_response(response)
    finish_reason = result.finish_reason
    if agent._should_treat_stop_as_truncated(finish_reason, result, messages):
        agent._vprint(
            f"{agent.log_prefix}⚠️  Treating suspicious Ollama/GLM stop response as truncated",
            force=True,
        )
        return "length"
    return finish_reason


def _normalize_truncated_message(agent: Any, response: Any) -> Any:
    transport = agent._get_transport()
    if agent.api_mode == "anthropic_messages":
        return transport.normalize_response(
            response,
            strip_tool_prefix=agent._is_anthropic_oauth,
        )
    return transport.normalize_response(response)


def _thinking_exhausted(
    agent: Any,
    trunc_content: Any,
    trunc_has_tool_calls: bool,
) -> bool:
    has_think_tags = bool(
        trunc_content
        and re.search(
            r"<(?:think|thinking|reasoning|REASONING_SCRATCHPAD)[^>]*>",
            trunc_content,
            re.IGNORECASE,
        )
    )
    return (
        not trunc_has_tool_calls
        and has_think_tags
        and (
            (trunc_content is not None and not agent._has_content_after_think_block(trunc_content))
            or trunc_content is None
        )
    )


def _thinking_exhausted_result(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    effective_task_id: str,
    api_call_count: int,
    finish_reason: str,
    length_continue_retries: int,
    truncated_tool_call_retries: int,
    truncated_response_parts: List[str],
) -> LengthRecoveryResult:
    error = (
        "Model used all output tokens on reasoning with none left for the response. "
        "Try lowering reasoning effort or increasing max_tokens."
    )
    agent._vprint(
        f"{agent.log_prefix}💭 Reasoning exhausted the output token budget — "
        "no visible response was produced.",
        force=True,
    )
    response_text = (
        "⚠️ **Thinking Budget Exhausted**\n\n"
        "The model used all its output tokens on reasoning "
        "and had none left for the actual response.\n\n"
        "To fix this:\n"
        "→ Lower reasoning effort: `/thinkon low` or `/thinkon minimal`\n"
        "→ Or switch to a larger/non-reasoning model with `/model`"
    )
    agent._cleanup_task_resources(effective_task_id)
    agent._persist_session(messages, conversation_history)
    return LengthRecoveryResult(
        "return",
        finish_reason,
        length_continue_retries,
        truncated_tool_call_retries,
        truncated_response_parts,
        False,
        {
            "final_response": response_text,
            "messages": messages,
            "api_calls": api_call_count,
            "completed": False,
            "partial": True,
            "error": error,
        },
    )


def _text_continuation_result(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    effective_task_id: str,
    api_call_count: int,
    finish_reason: str,
    length_continue_retries: int,
    truncated_tool_call_retries: int,
    truncated_response_parts: List[str],
    assistant_message: Any,
) -> LengthRecoveryResult:
    length_continue_retries += 1
    messages.append(agent._build_assistant_message(assistant_message, finish_reason))
    if assistant_message.content:
        truncated_response_parts.append(assistant_message.content)
    if length_continue_retries < 3:
        agent._vprint(
            f"{agent.log_prefix}↻ Requesting continuation ({length_continue_retries}/3)..."
        )
        messages.append(
            {
                "role": "user",
                "content": (
                    "[System: Your previous response was truncated by the output "
                    "length limit. Continue exactly where you left off. Do not "
                    "restart or repeat prior text. Finish the answer directly.]"
                ),
            }
        )
        agent._session_messages = messages
        return LengthRecoveryResult(
            "break_retry",
            finish_reason,
            length_continue_retries,
            truncated_tool_call_retries,
            truncated_response_parts,
            True,
        )

    partial = agent._strip_think_blocks("".join(truncated_response_parts)).strip()
    if partial:
        partial = (
            partial
            + "\n\n⚠️ 답변이 길이 제한에 걸려 여기까지 전달했어. "
            "작업 결과를 잃지 않도록 부분 결과를 먼저 보냈고, 이어서 물어보면 바로 계속 정리할게."
        )
    else:
        partial = (
            "⚠️ 답변이 출력 길이 제한에 걸려 완성본을 만들지 못했어. "
            "작업 자체는 중단하지 않았고, 다음 메시지에서 이어서 정리할 수 있어."
        )
    agent._cleanup_task_resources(effective_task_id)
    agent._persist_session(messages, conversation_history)
    return LengthRecoveryResult(
        "return",
        finish_reason,
        length_continue_retries,
        truncated_tool_call_retries,
        truncated_response_parts,
        False,
        {
            "final_response": partial,
            "messages": messages,
            "api_calls": api_call_count,
            "completed": False,
            "partial": True,
            "error": "Response remained truncated after 3 continuation attempts",
        },
    )


def _truncated_tool_call_result(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    effective_task_id: str,
    api_call_count: int,
    finish_reason: str,
    length_continue_retries: int,
    truncated_tool_call_retries: int,
    truncated_response_parts: List[str],
) -> LengthRecoveryResult:
    if truncated_tool_call_retries < 1:
        truncated_tool_call_retries += 1
        agent._vprint(
            f"{agent.log_prefix}⚠️  Truncated tool call detected — retrying API call...",
            force=True,
        )
        return LengthRecoveryResult(
            "continue",
            finish_reason,
            length_continue_retries,
            truncated_tool_call_retries,
            truncated_response_parts,
            False,
        )
    agent._vprint(
        f"{agent.log_prefix}⚠️  Truncated tool call response detected again — "
        "refusing to execute incomplete tool arguments.",
        force=True,
    )
    agent._cleanup_task_resources(effective_task_id)
    agent._persist_session(messages, conversation_history)
    return LengthRecoveryResult(
        "return",
        finish_reason,
        length_continue_retries,
        truncated_tool_call_retries,
        truncated_response_parts,
        False,
        {
            "final_response": None,
            "messages": messages,
            "api_calls": api_call_count,
            "completed": False,
            "partial": True,
            "error": "Response truncated due to output length limit",
        },
    )


def _rollback_or_fail_first_truncation(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
    finish_reason: str,
    length_continue_retries: int,
    truncated_tool_call_retries: int,
    truncated_response_parts: List[str],
    effective_task_id: str,
) -> LengthRecoveryResult:
    if len(messages) > 1:
        agent._vprint(
            f"{agent.log_prefix}   ⏪ Output was truncated after prior work; "
            "returning a user-visible checkpoint instead of going silent"
        )
        rolled_back_messages = agent._get_messages_up_to_last_assistant(messages)
        agent._cleanup_task_resources(effective_task_id)
        agent._persist_session(messages, conversation_history)
        return LengthRecoveryResult(
            "return",
            finish_reason,
            length_continue_retries,
            truncated_tool_call_retries,
            truncated_response_parts,
            False,
            {
                "final_response": (
                    "⚠️ 답변이 출력 길이 제한에 걸려 마지막 문장을 완성하지 못했어. "
                    "그래도 작업 결과를 잃지 않도록 여기서 멈췄다고 알려줄게. "
                    "바로 다음 메시지에서 이전 도구 결과를 이어 받아 정리할 수 있어."
                ),
                "messages": rolled_back_messages,
                "api_calls": api_call_count,
                "completed": False,
                "partial": True,
                "error": "Response truncated due to output length limit",
            },
        )

    agent._vprint(f"{agent.log_prefix}❌ First response truncated - cannot recover", force=True)
    agent._persist_session(messages, conversation_history)
    return LengthRecoveryResult(
        "return",
        finish_reason,
        length_continue_retries,
        truncated_tool_call_retries,
        truncated_response_parts,
        False,
        {
            "final_response": (
                "⚠️ 첫 답변이 출력 길이 제한에 걸려 완성되지 못했어. "
                "작업이 조용히 사라지지 않도록 실패 상태를 먼저 전달했어. "
                "짧게 다시 요청하거나, 이어서 요약하라고 보내줘."
            ),
            "messages": messages,
            "api_calls": api_call_count,
            "completed": False,
            "failed": True,
            "error": "First response truncated due to output length limit",
        },
    )
