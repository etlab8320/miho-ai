"""Tool-call response handling for one conversation turn."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from agent.model_metadata import estimate_request_tokens_rough

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolResponseResult:
    action: str
    messages: List[Dict[str, Any]]
    conversation_history: List[Dict[str, Any]] | None
    active_system_prompt: str | None
    truncated_tool_call_retries: int
    final_response: str | None = None
    turn_exit_reason: str = ""
    return_value: Dict[str, Any] | None = None


def handle_tool_response(
    *,
    agent: Any,
    assistant_message: Any,
    finish_reason: str,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    active_system_prompt: str | None,
    system_message: str | None,
    effective_task_id: str,
    api_call_count: int,
    truncated_tool_call_retries: int,
) -> ToolResponseResult:
    """Validate and execute assistant tool calls."""

    if not agent.quiet_mode:
        agent._vprint(
            f"{agent.log_prefix}🔧 Processing "
            f"{len(assistant_message.tool_calls)} tool call(s)..."
        )

    if agent.verbose_logging:
        for tc in assistant_message.tool_calls:
            logging.debug(
                "Tool call: %s with args: %s...",
                tc.function.name,
                tc.function.arguments[:200],
            )

    _repair_tool_names(agent, assistant_message)
    invalid_result = _handle_invalid_tool_names(
        agent=agent,
        assistant_message=assistant_message,
        finish_reason=finish_reason,
        messages=messages,
        conversation_history=conversation_history,
        active_system_prompt=active_system_prompt,
        truncated_tool_call_retries=truncated_tool_call_retries,
        api_call_count=api_call_count,
    )
    if invalid_result is not None:
        return invalid_result

    agent._invalid_tool_retries = 0

    invalid_json_args = _normalize_and_validate_arguments(assistant_message)
    json_result = _handle_invalid_json_arguments(
        agent=agent,
        assistant_message=assistant_message,
        finish_reason=finish_reason,
        messages=messages,
        conversation_history=conversation_history,
        active_system_prompt=active_system_prompt,
        truncated_tool_call_retries=truncated_tool_call_retries,
        invalid_json_args=invalid_json_args,
        api_call_count=api_call_count,
        effective_task_id=effective_task_id,
    )
    if json_result is not None:
        return json_result

    agent._invalid_json_retries = 0
    assistant_message.tool_calls = agent._cap_delegate_task_calls(
        assistant_message.tool_calls
    )
    assistant_message.tool_calls = agent._deduplicate_tool_calls(
        assistant_message.tool_calls
    )

    assistant_msg = agent._build_assistant_message(assistant_message, finish_reason)
    _capture_content_with_tools(agent, assistant_message)
    _drop_thinking_prefill_before_tool_success(agent, messages)

    agent._post_tool_empty_retried = False
    messages.append(assistant_msg)
    agent._emit_interim_assistant_message(assistant_msg)
    _close_stream_display(agent)

    agent._execute_tool_calls(
        assistant_message,
        messages,
        effective_task_id,
        api_call_count,
    )

    if agent._tool_guardrail_halt_decision is not None:
        decision = agent._tool_guardrail_halt_decision
        final_response = agent._toolguard_controlled_halt_response(decision)
        agent._emit_status(f"⚠️ Tool guardrail halted {decision.tool_name}: {decision.code}")
        messages.append({"role": "assistant", "content": final_response})
        return _result(
            "break",
            messages,
            conversation_history,
            active_system_prompt,
            truncated_tool_call_retries,
            final_response=final_response,
            turn_exit_reason="guardrail_halt",
        )

    truncated_tool_call_retries = 0
    agent._stream_needs_break = True
    _refund_programmatic_tool_budget(agent, assistant_message)
    messages, active_system_prompt, conversation_history = _compress_after_tools(
        agent=agent,
        messages=messages,
        active_system_prompt=active_system_prompt,
        conversation_history=conversation_history,
        system_message=system_message,
        effective_task_id=effective_task_id,
    )
    agent._session_messages = messages
    return _result(
        "continue",
        messages,
        conversation_history,
        active_system_prompt,
        truncated_tool_call_retries,
    )


def _repair_tool_names(agent: Any, assistant_message: Any) -> None:
    for tc in assistant_message.tool_calls:
        if tc.function.name in agent.valid_tool_names:
            continue
        repaired = agent._repair_tool_call(tc.function.name)
        if repaired:
            print(
                f"{agent.log_prefix}🔧 Auto-repaired tool name: "
                f"'{tc.function.name}' -> '{repaired}'"
            )
            tc.function.name = repaired


def _handle_invalid_tool_names(
    *,
    agent: Any,
    assistant_message: Any,
    finish_reason: str,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    active_system_prompt: str | None,
    truncated_tool_call_retries: int,
    api_call_count: int,
) -> ToolResponseResult | None:
    invalid_tool_calls = [
        tc.function.name for tc in assistant_message.tool_calls
        if tc.function.name not in agent.valid_tool_names
    ]
    if not invalid_tool_calls:
        return None

    agent._invalid_tool_retries += 1
    available = ", ".join(sorted(agent.valid_tool_names))
    invalid_name = invalid_tool_calls[0]
    invalid_preview = invalid_name[:80] + "..." if len(invalid_name) > 80 else invalid_name
    agent._vprint(
        f"{agent.log_prefix}⚠️  Unknown tool '{invalid_preview}' — "
        f"sending error to model for agent-correction "
        f"({agent._invalid_tool_retries}/3)"
    )

    if agent._invalid_tool_retries >= 3:
        agent._vprint(
            f"{agent.log_prefix}❌ Max retries (3) for invalid tool calls "
            "exceeded. Stopping as partial.",
            force=True,
        )
        agent._invalid_tool_retries = 0
        agent._persist_session(messages, conversation_history)
        return _result(
            "return",
            messages,
            conversation_history,
            active_system_prompt,
            truncated_tool_call_retries,
            return_value={
                "final_response": None,
                "messages": messages,
                "api_calls": api_call_count,
                "completed": False,
                "partial": True,
                "error": f"Model generated invalid tool call: {invalid_preview}",
            },
        )

    assistant_msg = agent._build_assistant_message(assistant_message, finish_reason)
    messages.append(assistant_msg)
    for tc in assistant_message.tool_calls:
        if tc.function.name not in agent.valid_tool_names:
            content = f"Tool '{tc.function.name}' does not exist. Available tools: {available}"
        else:
            content = (
                "Skipped: another tool call in this turn used an invalid name. "
                "Please retry this tool call."
            )
        messages.append({
            "role": "tool",
            "name": tc.function.name,
            "tool_call_id": tc.id,
            "content": content,
        })
    return _result(
        "continue",
        messages,
        conversation_history,
        active_system_prompt,
        truncated_tool_call_retries,
    )


def _normalize_and_validate_arguments(assistant_message: Any) -> List[tuple[str, str]]:
    invalid_json_args = []
    for tc in assistant_message.tool_calls:
        args = tc.function.arguments
        if isinstance(args, (dict, list)):
            tc.function.arguments = json.dumps(args)
            continue
        if args is not None and not isinstance(args, str):
            tc.function.arguments = str(args)
            args = tc.function.arguments
        if not args or not args.strip():
            tc.function.arguments = "{}"
            continue
        try:
            json.loads(args)
        except json.JSONDecodeError as exc:
            invalid_json_args.append((tc.function.name, str(exc)))
    return invalid_json_args


def _handle_invalid_json_arguments(
    *,
    agent: Any,
    assistant_message: Any,
    finish_reason: str,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    active_system_prompt: str | None,
    truncated_tool_call_retries: int,
    invalid_json_args: List[tuple[str, str]],
    api_call_count: int,
    effective_task_id: str,
) -> ToolResponseResult | None:
    if not invalid_json_args:
        return None
    if _tool_args_look_truncated(assistant_message, invalid_json_args):
        agent._vprint(
            f"{agent.log_prefix}⚠️  Truncated tool call arguments detected "
            f"(finish_reason={finish_reason!r}) — refusing to execute.",
            force=True,
        )
        agent._invalid_json_retries = 0
        agent._cleanup_task_resources(effective_task_id)
        agent._persist_session(messages, conversation_history)
        return _result(
            "return",
            messages,
            conversation_history,
            active_system_prompt,
            truncated_tool_call_retries,
            return_value={
                "final_response": None,
                "messages": messages,
                "api_calls": api_call_count,
                "completed": False,
                "partial": True,
                "error": "Response truncated due to output length limit",
            },
        )

    agent._invalid_json_retries += 1
    tool_name, error_msg = invalid_json_args[0]
    agent._vprint(
        f"{agent.log_prefix}⚠️  Invalid JSON in tool call arguments "
        f"for '{tool_name}': {error_msg}"
    )
    if agent._invalid_json_retries < 3:
        agent._vprint(
            f"{agent.log_prefix}🔄 Retrying API call "
            f"({agent._invalid_json_retries}/3)..."
        )
        return _result(
            "continue",
            messages,
            conversation_history,
            active_system_prompt,
            truncated_tool_call_retries,
        )

    agent._vprint(f"{agent.log_prefix}⚠️  Injecting recovery tool results for invalid JSON...")
    agent._invalid_json_retries = 0
    recovery_assistant = agent._build_assistant_message(assistant_message, finish_reason)
    messages.append(recovery_assistant)
    invalid_names = {name for name, _ in invalid_json_args}
    for tc in assistant_message.tool_calls:
        if tc.function.name in invalid_names:
            err = next(e for n, e in invalid_json_args if n == tc.function.name)
            tool_result = (
                f"Error: Invalid JSON arguments. {err}. "
                f"For tools with no required parameters, use an empty object: {{}}. "
                f"Please retry with valid JSON."
            )
        else:
            tool_result = "Skipped: other tool call in this response had invalid JSON."
        messages.append({
            "role": "tool",
            "name": tc.function.name,
            "tool_call_id": tc.id,
            "content": tool_result,
        })
    return _result(
        "continue",
        messages,
        conversation_history,
        active_system_prompt,
        truncated_tool_call_retries,
    )


def _tool_args_look_truncated(
    assistant_message: Any,
    invalid_json_args: List[tuple[str, str]],
) -> bool:
    invalid_names = {name for name, _ in invalid_json_args}
    return any(
        not (tc.function.arguments or "").rstrip().endswith(("}", "]"))
        for tc in assistant_message.tool_calls
        if tc.function.name in invalid_names
    )


def _capture_content_with_tools(agent: Any, assistant_message: Any) -> None:
    turn_content = assistant_message.content or ""
    if not (turn_content and agent._has_content_after_think_block(turn_content)):
        return
    agent._last_content_with_tools = turn_content
    housekeeping_tools = frozenset({"memory", "todo", "skill_manage", "session_search"})
    all_housekeeping = all(
        tc.function.name in housekeeping_tools
        for tc in assistant_message.tool_calls
    )
    agent._last_content_tools_all_housekeeping = all_housekeeping
    if all_housekeeping and agent._has_stream_consumers():
        agent._mute_post_response = True
    elif agent._should_emit_quiet_tool_messages():
        clean = agent._strip_think_blocks(turn_content).strip()
        if clean:
            agent._vprint(f"  ┊ 💬 {clean}")


def _drop_thinking_prefill_before_tool_success(
    agent: Any,
    messages: List[Dict[str, Any]],
) -> None:
    had_prefill = False
    while messages and isinstance(messages[-1], dict) and messages[-1].get("_thinking_prefill"):
        messages.pop()
        had_prefill = True
    if had_prefill:
        agent._thinking_prefill_retries = 0
        agent._empty_content_retries = 0


def _close_stream_display(agent: Any) -> None:
    if not agent.stream_delta_callback:
        return
    try:
        agent.stream_delta_callback(None)
    except Exception:
        pass


def _refund_programmatic_tool_budget(agent: Any, assistant_message: Any) -> None:
    tool_names = {tc.function.name for tc in assistant_message.tool_calls}
    if tool_names == {"execute_code"}:
        agent.iteration_budget.refund()


def _compress_after_tools(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    active_system_prompt: str | None,
    conversation_history: List[Dict[str, Any]] | None,
    system_message: str | None,
    effective_task_id: str,
) -> tuple[List[Dict[str, Any]], str | None, List[Dict[str, Any]] | None]:
    compressor = agent.context_compressor
    if compressor.last_prompt_tokens > 0:
        real_tokens = compressor.last_prompt_tokens
    else:
        real_tokens = estimate_request_tokens_rough(messages, tools=agent.tools or None)

    if not (agent.compression_enabled and compressor.should_compress(real_tokens)):
        return messages, active_system_prompt, conversation_history

    agent._safe_print("  ⟳ compacting context…")
    messages, active_system_prompt = agent._compress_context(
        messages,
        system_message,
        approx_tokens=agent.context_compressor.last_prompt_tokens,
        task_id=effective_task_id,
    )
    return messages, active_system_prompt, None


def _result(
    action: str,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    active_system_prompt: str | None,
    truncated_tool_call_retries: int,
    *,
    final_response: str | None = None,
    turn_exit_reason: str = "",
    return_value: Dict[str, Any] | None = None,
) -> ToolResponseResult:
    return ToolResponseResult(
        action=action,
        messages=messages,
        conversation_history=conversation_history,
        active_system_prompt=active_system_prompt,
        truncated_tool_call_retries=truncated_tool_call_retries,
        final_response=final_response,
        turn_exit_reason=turn_exit_reason,
        return_value=return_value,
    )
