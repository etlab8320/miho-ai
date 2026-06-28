"""API request preparation for the conversation turn loop."""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from typing import Any, Dict, List

from agent.display import KawaiiSpinner
from agent.memory_manager import build_memory_context_block
from agent.message_sanitization import (
    _repair_tool_call_arguments,
    _sanitize_messages_surrogates,
)
from agent.model_metadata import (
    estimate_messages_tokens_rough,
    estimate_request_tokens_rough,
)
from agent.prompt_caching import apply_anthropic_cache_control

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiRequestPreparation:
    api_messages: List[Dict[str, Any]]
    total_chars: int
    approx_tokens: int
    approx_request_tokens: int
    runtime_context_error: str | None
    thinking_spinner: Any | None


def prepare_api_request(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    current_turn_user_idx: int,
    active_system_prompt: str | None,
    plugin_user_context: str,
    ext_prefetch_cache: str,
    api_call_count: int,
    runtime_context_error: Any,
) -> ApiRequestPreparation:
    """Build API messages and start the quiet-mode spinner if needed."""

    _drain_pre_api_steer(agent, messages)
    request_logger = getattr(agent, "logger", None) or logging.getLogger(__name__)
    repaired_tool_calls = agent._sanitize_tool_call_arguments(
        messages,
        logger=request_logger,
        session_id=agent.session_id,
    )
    if repaired_tool_calls > 0:
        request_logger.info(
            "Sanitized %s corrupted tool_call arguments before request (session=%s)",
            repaired_tool_calls,
            agent.session_id or "-",
        )
    repaired_seq = agent._repair_message_sequence(messages)
    if repaired_seq > 0:
        request_logger.info(
            "Repaired %s message-alternation violations before request (session=%s)",
            repaired_seq,
            agent.session_id or "-",
        )
    api_messages = _build_api_messages(
        agent=agent,
        messages=messages,
        current_turn_user_idx=current_turn_user_idx,
        active_system_prompt=active_system_prompt,
        plugin_user_context=plugin_user_context,
        ext_prefetch_cache=ext_prefetch_cache,
    )
    _sanitize_messages_surrogates(api_messages)
    total_chars = sum(len(str(msg)) for msg in api_messages)
    approx_tokens = estimate_messages_tokens_rough(api_messages)
    approx_request_tokens = estimate_request_tokens_rough(
        api_messages, tools=agent.tools or None
    )
    context_error = runtime_context_error(agent, approx_request_tokens)
    thinking_spinner = _start_thinking_indicator(
        agent=agent,
        api_call_count=api_call_count,
        api_messages=api_messages,
        approx_tokens=approx_tokens,
        total_chars=total_chars,
    )
    return ApiRequestPreparation(
        api_messages=api_messages,
        total_chars=total_chars,
        approx_tokens=approx_tokens,
        approx_request_tokens=approx_request_tokens,
        runtime_context_error=context_error,
        thinking_spinner=thinking_spinner,
    )


def _drain_pre_api_steer(agent: Any, messages: List[Dict[str, Any]]) -> None:
    pre_api_steer = agent._drain_pending_steer()
    if not pre_api_steer:
        return
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        if isinstance(msg, dict) and msg.get("role") == "tool":
            marker = f"\n\nUser guidance: {pre_api_steer}"
            existing = msg.get("content", "")
            if isinstance(existing, str):
                msg["content"] = existing + marker
            else:
                try:
                    blocks = list(existing) if existing else []
                    blocks.append({"type": "text", "text": marker})
                    msg["content"] = blocks
                except Exception:
                    pass
            logger.debug(
                "Pre-API-call steer drain: injected into tool msg at index %d",
                idx,
            )
            return
    _put_back_pending_steer(agent, pre_api_steer)


def _put_back_pending_steer(agent: Any, steer: str) -> None:
    lock = getattr(agent, "_pending_steer_lock", None)
    if lock is not None:
        with lock:
            if agent._pending_steer:
                agent._pending_steer = agent._pending_steer + "\n" + steer
            else:
                agent._pending_steer = steer
        return
    existing = getattr(agent, "_pending_steer", None)
    agent._pending_steer = (existing + "\n" + steer) if existing else steer


def _build_api_messages(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    current_turn_user_idx: int,
    active_system_prompt: str | None,
    plugin_user_context: str,
    ext_prefetch_cache: str,
) -> List[Dict[str, Any]]:
    api_messages = [
        _api_message_for_turn(
            agent=agent,
            msg=msg,
            idx=idx,
            current_turn_user_idx=current_turn_user_idx,
            plugin_user_context=plugin_user_context,
            ext_prefetch_cache=ext_prefetch_cache,
        )
        for idx, msg in enumerate(messages)
    ]
    effective_system = active_system_prompt or ""
    if agent.ephemeral_system_prompt:
        effective_system = (
            effective_system + "\n\n" + agent.ephemeral_system_prompt
        ).strip()
    if effective_system:
        api_messages = [{"role": "system", "content": effective_system}] + api_messages
    if agent.prefill_messages:
        sys_offset = 1 if (api_messages and api_messages[0].get("role") == "system") else 0
        for idx, prefill_message in enumerate(agent.prefill_messages):
            api_messages.insert(sys_offset + idx, prefill_message.copy())
    if agent._use_prompt_caching:
        api_messages = apply_anthropic_cache_control(
            api_messages,
            cache_ttl=agent._cache_ttl,
            native_anthropic=agent._use_native_cache_layout,
        )
    api_messages = agent._sanitize_api_messages(api_messages)
    api_messages = agent._drop_thinking_only_and_merge_users(api_messages)
    _normalize_api_messages(api_messages)
    return api_messages


def _api_message_for_turn(
    *,
    agent: Any,
    msg: Dict[str, Any],
    idx: int,
    current_turn_user_idx: int,
    plugin_user_context: str,
    ext_prefetch_cache: str,
) -> Dict[str, Any]:
    api_msg = msg.copy()
    if idx == current_turn_user_idx and msg.get("role") == "user":
        injections = []
        if ext_prefetch_cache:
            fenced = build_memory_context_block(ext_prefetch_cache)
            if fenced:
                injections.append(fenced)
        if plugin_user_context:
            injections.append(plugin_user_context)
        if injections:
            base = api_msg.get("content", "")
            if isinstance(base, str):
                api_msg["content"] = base + "\n\n" + "\n\n".join(injections)
    agent._copy_reasoning_content_for_api(msg, api_msg)
    api_msg.pop("reasoning", None)
    api_msg.pop("finish_reason", None)
    api_msg.pop("_thinking_prefill", None)
    if agent._should_sanitize_tool_calls():
        agent._sanitize_tool_calls_for_strict_api(api_msg)
    return api_msg


def _normalize_api_messages(api_messages: List[Dict[str, Any]]) -> None:
    for api_message in api_messages:
        if isinstance(api_message.get("content"), str):
            api_message["content"] = api_message["content"].strip()
    for api_message in api_messages:
        tool_calls = api_message.get("tool_calls")
        if not tool_calls:
            continue
        normalized_calls = []
        for tool_call in tool_calls:
            if isinstance(tool_call, dict) and "function" in tool_call:
                tool_call = _normalize_tool_call(tool_call)
            normalized_calls.append(tool_call)
        api_message["tool_calls"] = normalized_calls


def _normalize_tool_call(tool_call: Dict[str, Any]) -> Dict[str, Any]:
    try:
        args_obj = json.loads(tool_call["function"]["arguments"])
        return {
            **tool_call,
            "function": {
                **tool_call["function"],
                "arguments": json.dumps(
                    args_obj,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            },
        }
    except Exception:
        tool_call["function"]["arguments"] = _repair_tool_call_arguments(
            tool_call["function"]["arguments"],
            tool_call["function"].get("name", "?"),
        )
        return tool_call


def _start_thinking_indicator(
    *,
    agent: Any,
    api_call_count: int,
    api_messages: List[Dict[str, Any]],
    approx_tokens: int,
    total_chars: int,
) -> Any | None:
    if not agent.quiet_mode:
        agent._vprint(
            f"\n{agent.log_prefix}🔄 Making API call #{api_call_count}/{agent.max_iterations}..."
        )
        agent._vprint(
            f"{agent.log_prefix}   📊 Request size: {len(api_messages)} messages, "
            f"~{approx_tokens:,} tokens (~{total_chars:,} chars)"
        )
        agent._vprint(
            f"{agent.log_prefix}   🔧 Available tools: {len(agent.tools) if agent.tools else 0}"
        )
        return None
    face = random.choice(KawaiiSpinner.get_thinking_faces())
    verb = random.choice(KawaiiSpinner.get_thinking_verbs())
    if agent.thinking_callback:
        agent.thinking_callback(f"{face} {verb}...")
        return None
    if not agent._has_stream_consumers() and agent._should_start_quiet_spinner():
        spinner_type = random.choice(["brain", "sparkle", "pulse", "moon", "star"])
        spinner = KawaiiSpinner(
            f"{face} {verb}...",
            spinner_type=spinner_type,
            print_fn=agent._print_fn,
        )
        spinner.start()
        return spinner
    return None
