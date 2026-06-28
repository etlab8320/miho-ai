"""Thin conversation-turn orchestrator for ``run_agent.AIAgent``."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from agent.conversation_api_attempt import perform_api_attempt
from agent.conversation_api_request import prepare_api_request
from agent.conversation_api_success import record_successful_api_call
from agent.conversation_error_one_shot import handle_one_shot_error_recovery
from agent.conversation_error_preflight import handle_early_api_error_recovery
from agent.conversation_error_retry import handle_api_error_retry
from agent.conversation_iteration_support import (
    boost_length_continuation_budget,
    consume_iteration_slot,
    fire_step_callback,
    log_api_request,
    refund_api_iteration,
    track_skill_nudge,
)
from agent.conversation_length_recovery import handle_finish_reason_and_length
from agent.conversation_nous_preflight import handle_nous_rate_limit_preflight
from agent.conversation_processing_error import handle_response_processing_exception
from agent.conversation_response_processing import process_successful_response
from agent.conversation_response_validation import handle_response_validation
from agent.conversation_runtime_context import ollama_context_limit_error
from agent.conversation_turn_finalization import finish_conversation_turn
from agent.conversation_turn_setup import prepare_conversation_turn, _restore_or_build_system_prompt
from agent.error_classifier import classify_api_error
from agent.retry_utils import jittered_backoff

logger = logging.getLogger(__name__)


def _ra():
    import run_agent

    return run_agent


def run_conversation(
    agent: Any,
    user_message: str,
    system_message: str = None,
    conversation_history: List[Dict[str, Any]] = None,
    task_id: str = None,
    stream_callback: Optional[Callable[..., Any]] = None,
    persist_user_message: Optional[str] = None,
) -> Dict[str, Any]:
    """Run one complete user turn through model calls, tools, and finalization."""

    setup = prepare_conversation_turn(
        agent=agent,
        user_message=user_message,
        system_message=system_message,
        conversation_history=conversation_history,
        task_id=task_id,
        stream_callback=stream_callback,
        persist_user_message=persist_user_message,
    )
    if setup.codex_app_server_result is not None:
        return setup.codex_app_server_result

    user_message = setup.user_message
    effective_task_id = setup.effective_task_id
    messages = setup.messages
    conversation_history = setup.conversation_history
    original_user_message = setup.original_user_message
    should_review_memory = setup.should_review_memory
    active_system_prompt = setup.active_system_prompt
    current_turn_user_idx = setup.current_turn_user_idx
    plugin_user_context = setup.plugin_user_context
    ext_prefetch_cache = setup.ext_prefetch_cache

    api_call_count = 0
    final_response = None
    interrupted = False
    failed = False
    codex_ack_continuations = 0
    length_continue_retries = 0
    truncated_tool_call_retries = 0
    truncated_response_parts: List[str] = []
    compression_attempts = 0
    turn_exit_reason = "unknown"

    while (
        api_call_count < agent.max_iterations
        and agent.iteration_budget.remaining > 0
    ) or agent._budget_grace_call:
        agent._checkpoint_mgr.new_turn()

        if agent._interrupt_requested:
            interrupted = True
            turn_exit_reason = "interrupted_by_user"
            if not agent.quiet_mode:
                agent._safe_print("\n⚡ Breaking out of tool loop due to interrupt...")
            break

        api_call_count += 1
        agent._api_call_count = api_call_count
        agent._touch_activity(f"starting API call #{api_call_count}")

        if not consume_iteration_slot(agent):
            turn_exit_reason = "budget_exhausted"
            break

        fire_step_callback(agent, api_call_count, messages)
        track_skill_nudge(agent)

        request = prepare_api_request(
            agent=agent,
            messages=messages,
            current_turn_user_idx=current_turn_user_idx,
            active_system_prompt=active_system_prompt,
            plugin_user_context=plugin_user_context,
            ext_prefetch_cache=ext_prefetch_cache,
            api_call_count=api_call_count,
            runtime_context_error=ollama_context_limit_error,
        )
        api_messages = request.api_messages
        total_chars = request.total_chars
        approx_tokens = request.approx_tokens
        thinking_spinner = request.thinking_spinner

        if request.runtime_context_error:
            final_response = request.runtime_context_error
            failed = True
            turn_exit_reason = "ollama_runtime_context_too_small"
            messages.append({"role": "assistant", "content": final_response})
            agent._emit_status("❌ Ollama runtime context is too small for Miho tool use")
            refund_api_iteration(agent, api_call_count - 1)
            api_call_count -= 1
            break

        log_api_request(agent, messages, approx_tokens)
        api_start_time = time.time()
        retry_count = 0
        max_retries = agent._api_max_retries
        max_compression_attempts = 3
        primary_recovery_attempted = False
        recovered_with_pool = False
        restart_with_compressed_messages = False
        restart_with_length_continuation = False
        finish_reason = "stop"
        response = None
        api_kwargs = None

        codex_auth_retry_attempted = False
        anthropic_auth_retry_attempted = False
        nous_auth_retry_attempted = False
        copilot_auth_retry_attempted = False
        thinking_sig_retry_attempted = False
        invalid_encrypted_content_retry_attempted = False
        image_shrink_retry_attempted = False
        multimodal_tool_content_retry_attempted = False
        oauth_1m_beta_retry_attempted = False
        llama_cpp_grammar_retry_attempted = False
        has_retried_429 = False

        while retry_count < max_retries:
            nous_preflight = handle_nous_rate_limit_preflight(
                agent=agent,
                messages=messages,
                conversation_history=conversation_history,
                api_call_count=api_call_count,
            )
            if nous_preflight.action == "return":
                return nous_preflight.return_value
            if nous_preflight.action == "continue":
                retry_count = 0
                compression_attempts = 0
                primary_recovery_attempted = False
                continue

            try:
                attempt = perform_api_attempt(
                    agent=agent,
                    api_messages=api_messages,
                    messages=messages,
                    thinking_spinner=thinking_spinner,
                    effective_task_id=effective_task_id,
                    original_user_message=original_user_message,
                    api_call_count=api_call_count,
                    approx_tokens=approx_tokens,
                    total_chars=total_chars,
                )
                response = attempt.response
                api_kwargs = attempt.api_kwargs
                api_duration = attempt.api_duration
                thinking_spinner = attempt.thinking_spinner

                validation = handle_response_validation(
                    agent=agent,
                    response=response,
                    thinking_spinner=thinking_spinner,
                    retry_count=retry_count,
                    max_retries=max_retries,
                    compression_attempts=compression_attempts,
                    primary_recovery_attempted=primary_recovery_attempted,
                    api_duration=api_duration,
                    messages=messages,
                    conversation_history=conversation_history,
                    api_call_count=api_call_count,
                    backoff_fn=jittered_backoff,
                    time_module=time,
                )
                retry_count = validation.retry_count
                compression_attempts = validation.compression_attempts
                primary_recovery_attempted = validation.primary_recovery_attempted
                thinking_spinner = validation.thinking_spinner
                if validation.action == "return":
                    return validation.return_value
                if validation.action == "continue":
                    continue

                length_result = handle_finish_reason_and_length(
                    agent=agent,
                    response=response,
                    messages=messages,
                    conversation_history=conversation_history,
                    effective_task_id=effective_task_id,
                    api_call_count=api_call_count,
                    length_continue_retries=length_continue_retries,
                    truncated_tool_call_retries=truncated_tool_call_retries,
                    truncated_response_parts=truncated_response_parts,
                )
                finish_reason = length_result.finish_reason
                length_continue_retries = length_result.length_continue_retries
                truncated_tool_call_retries = length_result.truncated_tool_call_retries
                truncated_response_parts = length_result.truncated_response_parts
                if length_result.restart_with_length_continuation:
                    restart_with_length_continuation = True
                if length_result.action == "return":
                    return length_result.return_value
                if length_result.action == "continue":
                    continue
                if length_result.action == "break_retry":
                    break

                record_successful_api_call(
                    agent=agent,
                    response=response,
                    api_duration=api_duration,
                )
                has_retried_429 = False
                agent._touch_activity(f"API call #{api_call_count} completed")
                break

            except InterruptedError:
                if thinking_spinner:
                    thinking_spinner.stop("")
                    thinking_spinner = None
                if agent.thinking_callback:
                    agent.thinking_callback("")
                api_elapsed = time.time() - api_start_time
                agent._vprint(f"{agent.log_prefix}⚡ Interrupted during API call.", force=True)
                agent._persist_session(messages, conversation_history)
                interrupted = True
                final_response = (
                    "Operation interrupted: waiting for model response "
                    f"({api_elapsed:.1f}s elapsed)."
                )
                break

            except Exception as api_error:
                if thinking_spinner:
                    thinking_spinner.stop("(╥_╥) error, retrying...")
                    thinking_spinner = None
                if agent.thinking_callback:
                    agent.thinking_callback("")

                early_recovery = handle_early_api_error_recovery(
                    agent=agent,
                    api_error=api_error,
                    messages=messages,
                    api_messages=api_messages,
                    api_kwargs=api_kwargs,
                    active_system_prompt=active_system_prompt,
                )
                active_system_prompt = early_recovery.active_system_prompt
                if early_recovery.action == "continue":
                    continue

                status_code = getattr(api_error, "status_code", None)
                error_context = agent._extract_api_error_context(api_error)
                compressor = getattr(agent, "context_compressor", None)
                context_length = (
                    getattr(compressor, "context_length", 200000)
                    if compressor
                    else 200000
                )
                classified = classify_api_error(
                    api_error,
                    provider=getattr(agent, "provider", "") or "",
                    model=getattr(agent, "model", "") or "",
                    approx_tokens=approx_tokens,
                    context_length=context_length,
                    num_messages=len(api_messages) if api_messages else 0,
                )
                logger.debug(
                    "Error classified: reason=%s status=%s retryable=%s "
                    "compress=%s rotate=%s fallback=%s",
                    classified.reason.value,
                    classified.status_code,
                    classified.retryable,
                    classified.should_compress,
                    classified.should_rotate_credential,
                    classified.should_fallback,
                )

                one_shot = handle_one_shot_error_recovery(
                    agent=agent,
                    api_error=api_error,
                    classified=classified,
                    status_code=status_code,
                    error_context=error_context,
                    messages=messages,
                    api_messages=api_messages,
                    has_retried_429=has_retried_429,
                    image_shrink_retry_attempted=image_shrink_retry_attempted,
                    multimodal_tool_content_retry_attempted=multimodal_tool_content_retry_attempted,
                    oauth_1m_beta_retry_attempted=oauth_1m_beta_retry_attempted,
                    codex_auth_retry_attempted=codex_auth_retry_attempted,
                    nous_auth_retry_attempted=nous_auth_retry_attempted,
                    copilot_auth_retry_attempted=copilot_auth_retry_attempted,
                    anthropic_auth_retry_attempted=anthropic_auth_retry_attempted,
                    thinking_sig_retry_attempted=thinking_sig_retry_attempted,
                    invalid_encrypted_content_retry_attempted=invalid_encrypted_content_retry_attempted,
                    llama_cpp_grammar_retry_attempted=llama_cpp_grammar_retry_attempted,
                )
                recovered_with_pool = one_shot.recovered_with_pool
                has_retried_429 = one_shot.has_retried_429
                image_shrink_retry_attempted = one_shot.image_shrink_retry_attempted
                multimodal_tool_content_retry_attempted = (
                    one_shot.multimodal_tool_content_retry_attempted
                )
                oauth_1m_beta_retry_attempted = one_shot.oauth_1m_beta_retry_attempted
                codex_auth_retry_attempted = one_shot.codex_auth_retry_attempted
                nous_auth_retry_attempted = one_shot.nous_auth_retry_attempted
                copilot_auth_retry_attempted = one_shot.copilot_auth_retry_attempted
                anthropic_auth_retry_attempted = one_shot.anthropic_auth_retry_attempted
                thinking_sig_retry_attempted = one_shot.thinking_sig_retry_attempted
                invalid_encrypted_content_retry_attempted = (
                    one_shot.invalid_encrypted_content_retry_attempted
                )
                llama_cpp_grammar_retry_attempted = one_shot.llama_cpp_grammar_retry_attempted
                if one_shot.action == "continue":
                    continue

                retry_decision = handle_api_error_retry(
                    agent=agent,
                    api_error=api_error,
                    classified=classified,
                    status_code=status_code,
                    error_context=error_context,
                    messages=messages,
                    conversation_history=conversation_history,
                    active_system_prompt=active_system_prompt,
                    system_message=system_message,
                    approx_tokens=approx_tokens,
                    effective_task_id=effective_task_id,
                    api_call_count=api_call_count,
                    api_messages=api_messages,
                    api_kwargs=api_kwargs,
                    retry_count=retry_count,
                    max_retries=max_retries,
                    compression_attempts=compression_attempts,
                    max_compression_attempts=max_compression_attempts,
                    primary_recovery_attempted=primary_recovery_attempted,
                    recovered_with_pool=recovered_with_pool,
                    api_start_time=api_start_time,
                    backoff_fn=jittered_backoff,
                    time_module=time,
                    pool_may_recover_fn=lambda *args, **kwargs: _ra()._pool_may_recover_from_rate_limit(
                        *args, **kwargs
                    ),
                )
                retry_count = retry_decision.retry_count
                compression_attempts = retry_decision.compression_attempts
                primary_recovery_attempted = retry_decision.primary_recovery_attempted
                messages = retry_decision.messages
                conversation_history = retry_decision.conversation_history
                active_system_prompt = retry_decision.active_system_prompt
                if retry_decision.restart_with_compressed_messages:
                    restart_with_compressed_messages = True
                if retry_decision.action == "return":
                    return retry_decision.return_value
                if retry_decision.action == "continue":
                    continue
                if retry_decision.action == "break_retry":
                    break

        if interrupted:
            turn_exit_reason = "interrupted_during_api_call"
            break

        if restart_with_compressed_messages:
            api_call_count -= 1
            agent.iteration_budget.refund()
            retry_count += 1
            restart_with_compressed_messages = False
            continue

        if restart_with_length_continuation:
            boost_length_continuation_budget(agent, length_continue_retries)
            continue

        if response is None:
            turn_exit_reason = "all_retries_exhausted_no_response"
            print(f"{agent.log_prefix}❌ All API retries exhausted with no successful response.")
            agent._persist_session(messages, conversation_history)
            break

        try:
            processed = process_successful_response(
                agent=agent,
                response=response,
                api_duration=api_duration,
                api_messages=api_messages,
                messages=messages,
                conversation_history=conversation_history,
                active_system_prompt=active_system_prompt,
                system_message=system_message,
                effective_task_id=effective_task_id,
                user_message=user_message,
                api_call_count=api_call_count,
                length_continue_retries=length_continue_retries,
                truncated_tool_call_retries=truncated_tool_call_retries,
                truncated_response_parts=truncated_response_parts,
                codex_ack_continuations=codex_ack_continuations,
            )
            messages = processed.messages
            conversation_history = processed.conversation_history
            active_system_prompt = processed.active_system_prompt
            final_response = processed.final_response
            length_continue_retries = processed.length_continue_retries
            truncated_tool_call_retries = processed.truncated_tool_call_retries
            truncated_response_parts = processed.truncated_response_parts
            codex_ack_continuations = processed.codex_ack_continuations
            if processed.action == "return":
                return processed.return_value
            if processed.action == "continue":
                continue
            if processed.action == "break":
                turn_exit_reason = processed.turn_exit_reason
                break
        except Exception as exc:
            handled = handle_response_processing_exception(
                agent=agent,
                error=exc,
                messages=messages,
                api_call_count=api_call_count,
            )
            messages = handled.messages
            final_response = handled.final_response or final_response
            if handled.action == "break":
                turn_exit_reason = handled.turn_exit_reason
                break
            continue

    return finish_conversation_turn(
        agent=agent,
        user_message=user_message,
        original_user_message=original_user_message,
        messages=messages,
        conversation_history=conversation_history,
        effective_task_id=effective_task_id,
        final_response=final_response,
        api_call_count=api_call_count,
        failed=failed,
        interrupted=interrupted,
        turn_exit_reason=turn_exit_reason,
        should_review_memory=should_review_memory,
    )


__all__ = ["run_conversation"]
