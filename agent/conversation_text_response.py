"""No-tool assistant response handling for one conversation turn."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TextResponseResult:
    action: str
    final_response: str | None
    messages: List[Dict[str, Any]]
    codex_ack_continuations: int
    length_continue_retries: int
    truncated_response_parts: List[str]
    turn_exit_reason: str = ""
    return_value: Dict[str, Any] | None = None


def handle_text_response(
    *,
    agent: Any,
    assistant_message: Any,
    finish_reason: str,
    messages: List[Dict[str, Any]],
    user_message: str,
    api_call_count: int,
    codex_ack_continuations: int,
    length_continue_retries: int,
    truncated_response_parts: List[str],
) -> TextResponseResult:
    """Handle a model response with no tool calls."""

    final_response = assistant_message.content or ""
    agent._mute_post_response = False

    if not agent._has_content_after_think_block(final_response):
        recovery = _recover_empty_response(
            agent=agent,
            assistant_message=assistant_message,
            finish_reason=finish_reason,
            messages=messages,
            api_call_count=api_call_count,
            final_response=final_response,
        )
        if recovery is not None:
            return TextResponseResult(
                action=recovery.action,
                final_response=recovery.final_response,
                messages=messages,
                codex_ack_continuations=codex_ack_continuations,
                length_continue_retries=length_continue_retries,
                truncated_response_parts=truncated_response_parts,
                turn_exit_reason=recovery.turn_exit_reason,
                return_value=recovery.return_value,
            )

    agent._empty_content_retries = 0
    agent._thinking_prefill_retries = 0

    if _should_continue_codex_ack(
        agent=agent,
        user_message=user_message,
        assistant_content=final_response,
        messages=messages,
        codex_ack_continuations=codex_ack_continuations,
    ):
        codex_ack_continuations += 1
        interim_msg = agent._build_assistant_message(assistant_message, "incomplete")
        messages.append(interim_msg)
        agent._emit_interim_assistant_message(interim_msg)
        messages.append({
            "role": "user",
            "content": (
                "[System: Continue now. Execute the required tool calls and only "
                "send your final answer after completing the task.]"
            ),
        })
        agent._session_messages = messages
        return TextResponseResult(
            action="continue",
            final_response=final_response,
            messages=messages,
            codex_ack_continuations=codex_ack_continuations,
            length_continue_retries=length_continue_retries,
            truncated_response_parts=truncated_response_parts,
        )

    codex_ack_continuations = 0
    if truncated_response_parts:
        final_response = "".join(truncated_response_parts) + final_response
        truncated_response_parts = []
        length_continue_retries = 0

    final_response = agent._strip_think_blocks(final_response).strip()
    final_msg = agent._build_assistant_message(assistant_message, finish_reason)
    _drop_internal_scaffolding(messages)
    messages.append(final_msg)
    if not agent.quiet_mode:
        agent._safe_print(
            f"🎉 Conversation completed after {api_call_count} "
            "OpenAI-compatible API call(s)"
        )
    return TextResponseResult(
        action="break",
        final_response=final_response,
        messages=messages,
        codex_ack_continuations=codex_ack_continuations,
        length_continue_retries=length_continue_retries,
        truncated_response_parts=truncated_response_parts,
        turn_exit_reason=f"text_response(finish_reason={finish_reason})",
    )


@dataclass(frozen=True)
class _EmptyRecovery:
    action: str
    final_response: str | None = None
    turn_exit_reason: str = ""
    return_value: Dict[str, Any] | None = None


def _recover_empty_response(
    *,
    agent: Any,
    assistant_message: Any,
    finish_reason: str,
    messages: List[Dict[str, Any]],
    api_call_count: int,
    final_response: str,
) -> _EmptyRecovery | None:
    partial_streamed = getattr(agent, "_current_streamed_assistant_text", "") or ""
    if agent._has_content_after_think_block(partial_streamed):
        recovered = agent._strip_think_blocks(partial_streamed).strip()
        logger.info("Partial stream content delivered (%d chars) — using as final response", len(recovered))
        agent._emit_status("↻ Stream interrupted — using delivered content as final response")
        agent._response_was_previewed = True
        return _EmptyRecovery(
            "break",
            final_response=recovered,
            turn_exit_reason="partial_stream_recovery",
        )

    fallback = getattr(agent, "_last_content_with_tools", None)
    if fallback and getattr(agent, "_last_content_tools_all_housekeeping", False):
        logger.info("Empty follow-up after tool calls — using prior turn content as final response")
        agent._emit_status("↻ Empty response after tool calls — using earlier content as final answer")
        agent._last_content_with_tools = None
        agent._last_content_tools_all_housekeeping = False
        agent._empty_content_retries = 0
        final_response = agent._strip_think_blocks(fallback).strip()
        agent._response_was_previewed = True
        return _EmptyRecovery(
            "break",
            final_response=final_response,
            turn_exit_reason="fallback_prior_turn_content",
        )

    prior_was_tool = any(m.get("role") == "tool" for m in messages[-5:])
    has_inline_thinking = bool(
        re.search(r"<think>|<thinking>|<reasoning>", final_response or "", re.IGNORECASE)
    )
    if (
        prior_was_tool
        and not getattr(agent, "_post_tool_empty_retried", False)
        and not has_inline_thinking
    ):
        agent._post_tool_empty_retried = True
        agent._last_content_with_tools = None
        agent._last_content_tools_all_housekeeping = False
        logger.info("Empty response after tool calls — nudging model to continue processing")
        agent._emit_status("⚠️ Model returned empty after tool calls — nudging to continue")
        nudge_msg = agent._build_assistant_message(assistant_message, finish_reason)
        nudge_msg["content"] = "(empty)"
        nudge_msg["_empty_recovery_synthetic"] = True
        messages.append(nudge_msg)
        messages.append({
            "role": "user",
            "content": (
                "You just executed tool calls but returned an empty response. "
                "Please process the tool results above and continue with the task."
            ),
            "_empty_recovery_synthetic": True,
        })
        return _EmptyRecovery("continue")

    has_structured = bool(
        getattr(assistant_message, "reasoning", None)
        or getattr(assistant_message, "reasoning_content", None)
        or getattr(assistant_message, "reasoning_details", None)
        or has_inline_thinking
    )
    if has_structured and agent._thinking_prefill_retries < 2:
        agent._thinking_prefill_retries += 1
        logger.info(
            "Thinking-only response (no visible content) — prefilling to continue (%d/2)",
            agent._thinking_prefill_retries,
        )
        agent._emit_status(
            f"↻ Thinking-only response — prefilling to continue "
            f"({agent._thinking_prefill_retries}/2)"
        )
        interim_msg = agent._build_assistant_message(assistant_message, "incomplete")
        interim_msg["_thinking_prefill"] = True
        messages.append(interim_msg)
        agent._session_messages = messages
        return _EmptyRecovery("continue")

    truly_empty = not agent._strip_think_blocks(final_response).strip()
    prefill_exhausted = has_structured and agent._thinking_prefill_retries >= 2
    if (
        truly_empty
        and (not has_structured or prefill_exhausted)
        and agent._empty_content_retries < 3
    ):
        agent._empty_content_retries += 1
        logger.warning(
            "Empty response (no content or reasoning) — retry %d/3 (model=%s)",
            agent._empty_content_retries,
            agent.model,
        )
        agent._emit_status(
            f"⚠️ Empty response from model — retrying ({agent._empty_content_retries}/3)"
        )
        return _EmptyRecovery("continue")

    if truly_empty and agent._fallback_chain:
        logger.warning(
            "Empty response after %d retries — attempting fallback (model=%s, provider=%s)",
            agent._empty_content_retries,
            agent.model,
            agent.provider,
        )
        agent._emit_status("⚠️ Model returning empty responses — switching to fallback provider...")
        if agent._try_activate_fallback():
            agent._empty_content_retries = 0
            agent._emit_status(f"↻ Switched to fallback: {agent.model} ({agent.provider})")
            logger.info(
                "Fallback activated after empty responses: now using %s on %s",
                agent.model,
                agent.provider,
            )
            return _EmptyRecovery("continue")

    if truly_empty:
        reasoning_text = agent._extract_reasoning(assistant_message)
        agent._drop_trailing_empty_response_scaffolding(messages)
        assistant_msg = agent._build_assistant_message(assistant_message, finish_reason)
        assistant_msg["content"] = "(empty)"
        assistant_msg["_empty_terminal_sentinel"] = True
        messages.append(assistant_msg)
        _emit_empty_terminal_status(
            agent=agent,
            reasoning_text=reasoning_text,
        )
        return _EmptyRecovery(
            "break",
            final_response="(empty)",
            turn_exit_reason="empty_response_exhausted",
        )

    return None


def _emit_empty_terminal_status(*, agent: Any, reasoning_text: str) -> None:
    if reasoning_text:
        reasoning_preview = (
            reasoning_text[:500] + "..." if len(reasoning_text) > 500 else reasoning_text
        )
        logger.warning(
            "Reasoning-only response (no visible content) after exhausting "
            "retries and fallback. Reasoning: %s",
            reasoning_preview,
        )
        agent._emit_status(
            "⚠️ Model produced reasoning but no visible response after all retries. "
            "Returning empty."
        )
        return

    logger.warning(
        "Empty response (no content or reasoning) after %d retries. "
        "No fallback available. model=%s provider=%s",
        agent._empty_content_retries,
        agent.model,
        agent.provider,
    )
    agent._emit_status(
        "❌ Model returned no content after all retries"
        + (" and fallback attempts." if agent._fallback_chain else ". No fallback providers configured.")
    )


def _should_continue_codex_ack(
    *,
    agent: Any,
    user_message: str,
    assistant_content: str,
    messages: List[Dict[str, Any]],
    codex_ack_continuations: int,
) -> bool:
    return (
        agent.api_mode == "codex_responses"
        and agent.valid_tool_names
        and codex_ack_continuations < 2
        and agent._looks_like_codex_intermediate_ack(
            user_message=user_message,
            assistant_content=assistant_content,
            messages=messages,
        )
    )


def _drop_internal_scaffolding(messages: List[Dict[str, Any]]) -> None:
    while (
        messages
        and isinstance(messages[-1], dict)
        and (
            messages[-1].get("_thinking_prefill")
            or messages[-1].get("_empty_recovery_synthetic")
            or messages[-1].get("_empty_terminal_sentinel")
        )
    ):
        messages.pop()
