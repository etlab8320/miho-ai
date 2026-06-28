"""Turn finalization helpers for ``agent.conversation_loop``."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from agent.codex_responses_adapter import _summarize_user_message_for_log
from agent.final_output_hooks import apply_transform_llm_output_hooks

logger = logging.getLogger(__name__)


def finish_conversation_turn(
    *,
    agent: Any,
    user_message: Any,
    original_user_message: str,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    effective_task_id: str,
    final_response: str | None,
    api_call_count: int,
    failed: bool,
    interrupted: bool,
    turn_exit_reason: str,
    should_review_memory: bool,
) -> Dict[str, Any]:
    """Finalize one turn and build the public result payload."""

    final_response, turn_exit_reason = _handle_budget_exhaustion(
        agent=agent,
        messages=messages,
        effective_task_id=effective_task_id,
        final_response=final_response,
        api_call_count=api_call_count,
        turn_exit_reason=turn_exit_reason,
    )
    completed = (
        final_response is not None
        and api_call_count < agent.max_iterations
        and not failed
    )
    agent._save_trajectory(
        messages,
        _summarize_user_message_for_log(user_message),
        completed,
    )
    agent._cleanup_task_resources(effective_task_id)
    agent._drop_trailing_empty_response_scaffolding(messages)
    agent._persist_session(messages, conversation_history)
    _log_turn_exit(
        agent=agent,
        messages=messages,
        final_response=final_response,
        api_call_count=api_call_count,
        interrupted=interrupted,
        turn_exit_reason=turn_exit_reason,
    )
    final_response = _append_file_mutation_footer(
        agent=agent,
        final_response=final_response,
        interrupted=interrupted,
    )
    final_response = _apply_final_output_hooks(
        agent=agent,
        final_response=final_response,
        interrupted=interrupted,
        original_user_message=original_user_message,
        messages=messages,
    )
    _post_llm_call_hook(
        agent=agent,
        final_response=final_response,
        interrupted=interrupted,
        original_user_message=original_user_message,
        messages=messages,
    )
    result = _build_result(
        agent=agent,
        messages=messages,
        final_response=final_response,
        api_call_count=api_call_count,
        completed=completed,
        failed=failed,
        interrupted=interrupted,
        turn_exit_reason=turn_exit_reason,
    )
    _finish_runtime_side_effects(
        agent=agent,
        result=result,
        messages=messages,
        final_response=final_response,
        interrupted=interrupted,
        original_user_message=original_user_message,
        should_review_memory=should_review_memory,
    )
    _on_session_end_hook(
        agent=agent,
        completed=completed,
        interrupted=interrupted,
    )
    return result


def _handle_budget_exhaustion(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    effective_task_id: str,
    final_response: str | None,
    api_call_count: int,
    turn_exit_reason: str,
) -> tuple[str | None, str]:
    if final_response is not None:
        return final_response, turn_exit_reason
    if api_call_count < agent.max_iterations and agent.iteration_budget.remaining > 0:
        return final_response, turn_exit_reason
    turn_exit_reason = f"max_iterations_reached({api_call_count}/{agent.max_iterations})"
    agent._emit_status(
        f"⚠️ Iteration budget exhausted ({api_call_count}/{agent.max_iterations}) "
        "— asking model to summarise"
    )
    if not agent.quiet_mode:
        agent._safe_print(
            f"\n⚠️  Iteration budget exhausted ({api_call_count}/{agent.max_iterations}) "
            "— requesting summary..."
        )
    final_response = agent._handle_max_iterations(messages, api_call_count)
    _block_kanban_task_if_needed(
        agent=agent,
        effective_task_id=effective_task_id,
        api_call_count=api_call_count,
    )
    return final_response, turn_exit_reason


def _block_kanban_task_if_needed(
    *,
    agent: Any,
    effective_task_id: str,
    api_call_count: int,
) -> None:
    kanban_task = os.environ.get("MIHO_KANBAN_TASK")
    if not kanban_task:
        return
    try:
        _ra().handle_function_call(
            "kanban_block",
            {
                "task_id": kanban_task,
                "reason": (
                    f"Iteration budget exhausted ({api_call_count}/{agent.max_iterations}) — "
                    "task could not complete within the allowed iterations"
                ),
            },
            task_id=effective_task_id,
        )
        logger.info(
            "kanban_block called for task %s after iteration exhaustion (%d/%d)",
            kanban_task,
            api_call_count,
            agent.max_iterations,
        )
    except Exception:
        logger.warning(
            "Failed to call kanban_block after iteration exhaustion for task %s",
            kanban_task,
            exc_info=True,
        )


def _log_turn_exit(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    final_response: str | None,
    api_call_count: int,
    interrupted: bool,
    turn_exit_reason: str,
) -> None:
    last_msg_role = messages[-1].get("role") if messages else None
    last_tool_name = _last_tool_name(messages) if last_msg_role == "tool" else None
    turn_tool_count = sum(
        1
        for item in messages
        if isinstance(item, dict)
        and item.get("role") == "assistant"
        and item.get("tool_calls")
    )
    response_len = len(final_response) if final_response else 0
    budget_used = agent.iteration_budget.used if agent.iteration_budget else 0
    budget_max = agent.iteration_budget.max_total if agent.iteration_budget else 0
    diag_msg = (
        "Turn ended: reason=%s model=%s api_calls=%d/%d budget=%d/%d "
        "tool_turns=%d last_msg_role=%s response_len=%d session=%s"
    )
    diag_args = (
        turn_exit_reason,
        agent.model,
        api_call_count,
        agent.max_iterations,
        budget_used,
        budget_max,
        turn_tool_count,
        last_msg_role,
        response_len,
        agent.session_id or "none",
    )
    if last_msg_role == "tool" and not interrupted:
        logger.warning(
            "Turn ended with pending tool result (agent may appear stuck). "
            + diag_msg
            + " last_tool=%s",
            *diag_args,
            last_tool_name,
        )
        return
    logger.info(diag_msg, *diag_args)


def _last_tool_name(messages: List[Dict[str, Any]]) -> str | None:
    for item in reversed(messages):
        if item.get("role") == "assistant" and item.get("tool_calls"):
            tool_calls = item["tool_calls"]
            if tool_calls and isinstance(tool_calls[0], dict):
                return tool_calls[-1].get("function", {}).get("name")
            return None
    return None


def _append_file_mutation_footer(
    *,
    agent: Any,
    final_response: str | None,
    interrupted: bool,
) -> str | None:
    if not final_response or interrupted:
        return final_response
    try:
        failed_mutations = getattr(agent, "_turn_failed_file_mutations", None) or {}
        if failed_mutations and agent._file_mutation_verifier_enabled():
            footer = agent._format_file_mutation_failure_footer(failed_mutations)
            if footer:
                return final_response.rstrip() + "\n\n" + footer
    except Exception as exc:
        logger.debug("file-mutation verifier footer failed: %s", exc)
    return final_response


def _apply_final_output_hooks(
    *,
    agent: Any,
    final_response: str | None,
    interrupted: bool,
    original_user_message: str,
    messages: List[Dict[str, Any]],
) -> str | None:
    if not final_response or interrupted:
        return final_response
    return apply_transform_llm_output_hooks(
        response_text=final_response,
        user_message=original_user_message,
        conversation_history=list(messages),
        session_id=agent.session_id or "",
        model=agent.model,
        platform=getattr(agent, "platform", None) or "",
    )


def _post_llm_call_hook(
    *,
    agent: Any,
    final_response: str | None,
    interrupted: bool,
    original_user_message: str,
    messages: List[Dict[str, Any]],
) -> None:
    if not final_response or interrupted:
        return
    try:
        from miho_cli.plugins import invoke_hook as _invoke_hook

        _invoke_hook(
            "post_llm_call",
            session_id=agent.session_id,
            user_message=original_user_message,
            assistant_response=final_response,
            conversation_history=list(messages),
            model=agent.model,
            platform=getattr(agent, "platform", None) or "",
        )
    except Exception as exc:
        logger.warning("post_llm_call hook failed: %s", exc)


def _build_result(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    final_response: str | None,
    api_call_count: int,
    completed: bool,
    failed: bool,
    interrupted: bool,
    turn_exit_reason: str,
) -> Dict[str, Any]:
    result = {
        "final_response": final_response,
        "last_reasoning": _last_current_turn_reasoning(messages),
        "messages": messages,
        "api_calls": api_call_count,
        "completed": completed,
        "turn_exit_reason": turn_exit_reason,
        "failed": failed,
        "partial": False,
        "interrupted": interrupted,
        "response_previewed": getattr(agent, "_response_was_previewed", False),
        "model": agent.model,
        "provider": agent.provider,
        "base_url": agent.base_url,
        "input_tokens": agent.session_input_tokens,
        "output_tokens": agent.session_output_tokens,
        "cache_read_tokens": agent.session_cache_read_tokens,
        "cache_write_tokens": agent.session_cache_write_tokens,
        "reasoning_tokens": agent.session_reasoning_tokens,
        "prompt_tokens": agent.session_prompt_tokens,
        "completion_tokens": agent.session_completion_tokens,
        "total_tokens": agent.session_total_tokens,
        "last_prompt_tokens": getattr(agent.context_compressor, "last_prompt_tokens", 0) or 0,
        "estimated_cost_usd": agent.session_estimated_cost_usd,
        "cost_status": agent.session_cost_status,
        "cost_source": agent.session_cost_source,
    }
    if agent._tool_guardrail_halt_decision is not None:
        result["guardrail"] = agent._tool_guardrail_halt_decision.to_metadata()
    return result


def _last_current_turn_reasoning(messages: List[Dict[str, Any]]) -> Any:
    for item in reversed(messages):
        if item.get("role") == "user":
            break
        if item.get("role") == "assistant" and item.get("reasoning"):
            return item["reasoning"]
    return None


def _finish_runtime_side_effects(
    *,
    agent: Any,
    result: Dict[str, Any],
    messages: List[Dict[str, Any]],
    final_response: str | None,
    interrupted: bool,
    original_user_message: str,
    should_review_memory: bool,
) -> None:
    leftover_steer = agent._drain_pending_steer()
    if leftover_steer:
        result["pending_steer"] = leftover_steer
    agent._response_was_previewed = False
    if interrupted and agent._interrupt_message:
        result["interrupt_message"] = agent._interrupt_message
    agent.clear_interrupt()
    agent._stream_callback = None
    should_review_skills = _should_review_skills(agent)
    agent._sync_external_memory_for_turn(
        original_user_message=original_user_message,
        final_response=final_response,
        interrupted=interrupted,
    )
    if final_response and not interrupted and (should_review_memory or should_review_skills):
        try:
            agent._spawn_background_review(
                messages_snapshot=list(messages),
                review_memory=should_review_memory,
                review_skills=should_review_skills,
            )
        except Exception:
            pass


def _should_review_skills(agent: Any) -> bool:
    if not (
        agent._skill_nudge_interval > 0
        and agent._iters_since_skill >= agent._skill_nudge_interval
        and "skill_manage" in agent.valid_tool_names
    ):
        return False
    agent._iters_since_skill = 0
    return True


def _on_session_end_hook(
    *,
    agent: Any,
    completed: bool,
    interrupted: bool,
) -> None:
    try:
        from miho_cli.plugins import invoke_hook as _invoke_hook

        _invoke_hook(
            "on_session_end",
            session_id=agent.session_id,
            completed=completed,
            interrupted=interrupted,
            model=agent.model,
            platform=getattr(agent, "platform", None) or "",
        )
    except Exception as exc:
        logger.warning("on_session_end hook failed: %s", exc)


def _ra():
    import run_agent

    return run_agent
