"""Successful response post-processing for the conversation loop."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List

from agent.conversation_text_response import handle_text_response
from agent.conversation_tool_response import handle_tool_response
from agent.trajectory import has_incomplete_scratchpad

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResponseProcessingResult:
    action: str
    messages: List[Dict[str, Any]]
    conversation_history: List[Dict[str, Any]] | None
    active_system_prompt: str | None
    final_response: str | None
    turn_exit_reason: str
    length_continue_retries: int
    truncated_tool_call_retries: int
    truncated_response_parts: List[str]
    codex_ack_continuations: int
    return_value: Dict[str, Any] | None = None


def process_successful_response(
    *,
    agent: Any,
    response: Any,
    api_duration: float,
    api_messages: List[Dict[str, Any]],
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    active_system_prompt: str | None,
    system_message: str | None,
    effective_task_id: str,
    user_message: str,
    api_call_count: int,
    length_continue_retries: int,
    truncated_tool_call_retries: int,
    truncated_response_parts: List[str],
    codex_ack_continuations: int,
) -> ResponseProcessingResult:
    """Normalize and route one successful assistant response."""

    assistant_message, finish_reason = _normalize_response(agent, response)
    _invoke_post_api_request_hook(
        agent=agent,
        response=response,
        assistant_message=assistant_message,
        finish_reason=finish_reason,
        effective_task_id=effective_task_id,
        api_call_count=api_call_count,
        api_duration=api_duration,
        api_messages=api_messages,
    )
    _emit_assistant_progress(agent, assistant_message)

    scratchpad_result = _handle_incomplete_scratchpad(
        agent=agent,
        assistant_message=assistant_message,
        messages=messages,
        conversation_history=conversation_history,
        effective_task_id=effective_task_id,
        api_call_count=api_call_count,
    )
    if scratchpad_result is not None:
        return _wrap_static_result(
            scratchpad_result,
            messages,
            conversation_history,
            active_system_prompt,
            length_continue_retries,
            truncated_tool_call_retries,
            truncated_response_parts,
            codex_ack_continuations,
        )

    agent._incomplete_scratchpad_retries = 0
    codex_result = _handle_codex_incomplete(
        agent=agent,
        assistant_message=assistant_message,
        finish_reason=finish_reason,
        messages=messages,
        conversation_history=conversation_history,
        api_call_count=api_call_count,
    )
    if codex_result is not None:
        return _wrap_static_result(
            codex_result,
            messages,
            conversation_history,
            active_system_prompt,
            length_continue_retries,
            truncated_tool_call_retries,
            truncated_response_parts,
            codex_ack_continuations,
        )
    if hasattr(agent, "_codex_incomplete_retries"):
        agent._codex_incomplete_retries = 0

    if assistant_message.tool_calls:
        tool_result = handle_tool_response(
            agent=agent,
            assistant_message=assistant_message,
            finish_reason=finish_reason,
            messages=messages,
            conversation_history=conversation_history,
            active_system_prompt=active_system_prompt,
            system_message=system_message,
            effective_task_id=effective_task_id,
            api_call_count=api_call_count,
            truncated_tool_call_retries=truncated_tool_call_retries,
        )
        return ResponseProcessingResult(
            action=tool_result.action,
            messages=tool_result.messages,
            conversation_history=tool_result.conversation_history,
            active_system_prompt=tool_result.active_system_prompt,
            final_response=tool_result.final_response,
            turn_exit_reason=tool_result.turn_exit_reason,
            length_continue_retries=length_continue_retries,
            truncated_tool_call_retries=tool_result.truncated_tool_call_retries,
            truncated_response_parts=truncated_response_parts,
            codex_ack_continuations=codex_ack_continuations,
            return_value=tool_result.return_value,
        )

    text_result = handle_text_response(
        agent=agent,
        assistant_message=assistant_message,
        finish_reason=finish_reason,
        messages=messages,
        user_message=user_message,
        api_call_count=api_call_count,
        codex_ack_continuations=codex_ack_continuations,
        length_continue_retries=length_continue_retries,
        truncated_response_parts=truncated_response_parts,
    )
    return ResponseProcessingResult(
        action=text_result.action,
        messages=text_result.messages,
        conversation_history=conversation_history,
        active_system_prompt=active_system_prompt,
        final_response=text_result.final_response,
        turn_exit_reason=text_result.turn_exit_reason,
        length_continue_retries=text_result.length_continue_retries,
        truncated_tool_call_retries=truncated_tool_call_retries,
        truncated_response_parts=text_result.truncated_response_parts,
        codex_ack_continuations=text_result.codex_ack_continuations,
        return_value=text_result.return_value,
    )


def _normalize_response(agent: Any, response: Any) -> tuple[Any, str]:
    transport = agent._get_transport()
    normalize_kwargs = {}
    if agent.api_mode == "anthropic_messages":
        normalize_kwargs["strip_tool_prefix"] = agent._is_anthropic_oauth
    assistant_message = transport.normalize_response(response, **normalize_kwargs)
    finish_reason = assistant_message.finish_reason
    if assistant_message.content is not None and not isinstance(assistant_message.content, str):
        assistant_message.content = _content_to_text(assistant_message.content)
    return assistant_message, finish_reason


def _content_to_text(raw: Any) -> str:
    if isinstance(raw, dict):
        return raw.get("text", "") or raw.get("content", "") or json.dumps(raw)
    if isinstance(raw, list):
        parts = []
        for part in raw:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
            elif isinstance(part, dict) and "text" in part:
                parts.append(str(part["text"]))
        return "\n".join(parts)
    return str(raw)


def _invoke_post_api_request_hook(
    *,
    agent: Any,
    response: Any,
    assistant_message: Any,
    finish_reason: str,
    effective_task_id: str,
    api_call_count: int,
    api_duration: float,
    api_messages: List[Dict[str, Any]],
) -> None:
    try:
        from miho_cli.plugins import invoke_hook as invoke_hook

        assistant_tool_calls = getattr(assistant_message, "tool_calls", None) or []
        assistant_text = assistant_message.content or ""
        invoke_hook(
            "post_api_request",
            task_id=effective_task_id,
            session_id=agent.session_id or "",
            platform=agent.platform or "",
            model=agent.model,
            provider=agent.provider,
            base_url=agent.base_url,
            api_mode=agent.api_mode,
            api_call_count=api_call_count,
            api_duration=api_duration,
            finish_reason=finish_reason,
            message_count=len(api_messages),
            response_model=getattr(response, "model", None),
            response=response,
            usage=agent._usage_summary_for_api_request_hook(response),
            assistant_message=assistant_message,
            assistant_content_chars=len(assistant_text),
            assistant_tool_call_count=len(assistant_tool_calls),
        )
    except Exception:
        pass


def _emit_assistant_progress(agent: Any, assistant_message: Any) -> None:
    if assistant_message.content and not agent.quiet_mode:
        if agent.verbose_logging:
            agent._vprint(f"{agent.log_prefix}🤖 Assistant: {assistant_message.content}")
        else:
            preview = assistant_message.content[:100]
            suffix = "..." if len(assistant_message.content) > 100 else ""
            agent._vprint(f"{agent.log_prefix}🤖 Assistant: {preview}{suffix}")

    if not (assistant_message.content and agent.tool_progress_callback):
        return
    think_text = assistant_message.content.strip()
    think_text = re.sub(
        r"</?(?:REASONING_SCRATCHPAD|think|reasoning)>",
        "",
        think_text,
    ).strip()
    first_line = think_text.split("\n")[0][:80] if think_text else ""
    if first_line and getattr(agent, "_delegate_depth", 0) > 0:
        try:
            agent.tool_progress_callback("_thinking", first_line)
        except Exception:
            pass
    elif think_text:
        try:
            agent.tool_progress_callback(
                "reasoning.available",
                "_thinking",
                think_text[:500],
                None,
            )
        except Exception:
            pass


@dataclass(frozen=True)
class _StaticProcessingResult:
    action: str
    final_response: str | None = None
    turn_exit_reason: str = ""
    return_value: Dict[str, Any] | None = None


def _handle_incomplete_scratchpad(
    *,
    agent: Any,
    assistant_message: Any,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    effective_task_id: str,
    api_call_count: int,
) -> _StaticProcessingResult | None:
    if not has_incomplete_scratchpad(assistant_message.content or ""):
        return None
    agent._incomplete_scratchpad_retries += 1
    agent._vprint(
        f"{agent.log_prefix}⚠️  Incomplete <REASONING_SCRATCHPAD> detected "
        "(opened but never closed)"
    )
    if agent._incomplete_scratchpad_retries <= 2:
        agent._vprint(
            f"{agent.log_prefix}🔄 Retrying API call "
            f"({agent._incomplete_scratchpad_retries}/2)..."
        )
        return _StaticProcessingResult("continue")

    agent._vprint(
        f"{agent.log_prefix}❌ Max retries (2) for incomplete scratchpad. "
        "Saving as partial.",
        force=True,
    )
    agent._incomplete_scratchpad_retries = 0
    rolled_back_messages = agent._get_messages_up_to_last_assistant(messages)
    agent._cleanup_task_resources(effective_task_id)
    agent._persist_session(messages, conversation_history)
    return _StaticProcessingResult(
        "return",
        return_value={
            "final_response": None,
            "messages": rolled_back_messages,
            "api_calls": api_call_count,
            "completed": False,
            "partial": True,
            "error": "Incomplete REASONING_SCRATCHPAD after 2 retries",
        },
    )


def _handle_codex_incomplete(
    *,
    agent: Any,
    assistant_message: Any,
    finish_reason: str,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
) -> _StaticProcessingResult | None:
    if not (agent.api_mode == "codex_responses" and finish_reason == "incomplete"):
        return None

    agent._codex_incomplete_retries += 1
    interim_msg = agent._build_assistant_message(assistant_message, finish_reason)
    if _codex_interim_has_content(interim_msg):
        _append_distinct_codex_interim(agent, messages, interim_msg)

    if agent._codex_incomplete_retries < 3:
        if not agent.quiet_mode:
            agent._vprint(
                f"{agent.log_prefix}↻ Codex response incomplete; continuing turn "
                f"({agent._codex_incomplete_retries}/3)"
            )
        agent._session_messages = messages
        return _StaticProcessingResult("continue")

    agent._codex_incomplete_retries = 0
    agent._persist_session(messages, conversation_history)
    return _StaticProcessingResult(
        "return",
        return_value={
            "final_response": None,
            "messages": messages,
            "api_calls": api_call_count,
            "completed": False,
            "partial": True,
            "error": "Codex response remained incomplete after 3 continuation attempts",
        },
    )


def _codex_interim_has_content(interim_msg: Dict[str, Any]) -> bool:
    interim_has_content = bool((interim_msg.get("content") or "").strip())
    interim_has_reasoning = (
        bool(interim_msg.get("reasoning", "").strip())
        if isinstance(interim_msg.get("reasoning"), str)
        else False
    )
    return (
        interim_has_content
        or interim_has_reasoning
        or bool(interim_msg.get("codex_reasoning_items"))
        or bool(interim_msg.get("codex_message_items"))
    )


def _append_distinct_codex_interim(
    agent: Any,
    messages: List[Dict[str, Any]],
    interim_msg: Dict[str, Any],
) -> None:
    last_msg = messages[-1] if messages else None
    last_codex_items = last_msg.get("codex_reasoning_items") if isinstance(last_msg, dict) else None
    last_codex_message_items = last_msg.get("codex_message_items") if isinstance(last_msg, dict) else None
    duplicate_interim = (
        isinstance(last_msg, dict)
        and last_msg.get("role") == "assistant"
        and last_msg.get("finish_reason") == "incomplete"
        and (last_msg.get("content") or "") == (interim_msg.get("content") or "")
        and (last_msg.get("reasoning") or "") == (interim_msg.get("reasoning") or "")
        and last_codex_items == interim_msg.get("codex_reasoning_items")
        and last_codex_message_items == interim_msg.get("codex_message_items")
    )
    if not duplicate_interim:
        messages.append(interim_msg)
        agent._emit_interim_assistant_message(interim_msg)


def _wrap_static_result(
    static: _StaticProcessingResult,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    active_system_prompt: str | None,
    length_continue_retries: int,
    truncated_tool_call_retries: int,
    truncated_response_parts: List[str],
    codex_ack_continuations: int,
) -> ResponseProcessingResult:
    return ResponseProcessingResult(
        action=static.action,
        messages=messages,
        conversation_history=conversation_history,
        active_system_prompt=active_system_prompt,
        final_response=static.final_response,
        turn_exit_reason=static.turn_exit_reason,
        length_continue_retries=length_continue_retries,
        truncated_tool_call_retries=truncated_tool_call_retries,
        truncated_response_parts=truncated_response_parts,
        codex_ack_continuations=codex_ack_continuations,
        return_value=static.return_value,
    )
