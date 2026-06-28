"""Turn setup helpers for ``agent.conversation_loop``."""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent.auxiliary_client import set_runtime_main
from agent.codex_responses_adapter import _summarize_user_message_for_log
from agent.iteration_budget import IterationBudget
from agent.message_sanitization import _sanitize_surrogates
from agent.model_metadata import estimate_request_tokens_rough
from agent.process_bootstrap import _install_safe_stdio
from agent.prompt_builder import build_context_hooks_prompt
from agent.turn_context import begin_turn_context, set_current_user_message
from miho_logging import set_session_context
from tools.skill_provenance import set_current_write_origin

logger = logging.getLogger("agent.conversation_loop")


@dataclass(frozen=True)
class ConversationTurnSetup:
    user_message: str
    persist_user_message: str | None
    effective_task_id: str
    messages: List[Dict[str, Any]]
    conversation_history: List[Dict[str, Any]] | None
    original_user_message: str
    should_review_memory: bool
    active_system_prompt: str | None
    current_turn_user_idx: int
    plugin_user_context: str
    ext_prefetch_cache: str
    codex_app_server_result: Dict[str, Any] | None = None


def prepare_conversation_turn(
    *,
    agent: Any,
    user_message: str,
    system_message: str | None,
    conversation_history: List[Dict[str, Any]] | None,
    task_id: str | None,
    stream_callback: Optional[callable],
    persist_user_message: str | None,
) -> ConversationTurnSetup:
    """Prepare one user turn before the model/tool loop starts."""

    _install_safe_stdio()
    agent._ensure_db_session()
    _set_runtime_model(agent)
    set_session_context(agent.session_id)
    set_current_write_origin(getattr(agent, "_memory_write_origin", "assistant_tool"))
    agent._restore_primary_runtime()

    if isinstance(user_message, str):
        user_message = _sanitize_surrogates(user_message)
    if isinstance(persist_user_message, str):
        persist_user_message = _sanitize_surrogates(persist_user_message)

    agent._stream_callback = stream_callback
    agent._persist_user_message_idx = None
    agent._persist_user_message_override = persist_user_message
    effective_task_id = task_id or str(uuid.uuid4())
    begin_turn_context(effective_task_id)
    agent._current_task_id = effective_task_id
    _reset_turn_counters(agent)
    _cleanup_stale_connections(agent)
    _replay_compression_warning(agent)
    agent.iteration_budget = IterationBudget(agent.max_iterations)
    _log_turn_start(agent, user_message, conversation_history)

    messages = list(conversation_history) if conversation_history else []
    _hydrate_turn_state(agent, conversation_history)
    agent._user_turn_count += 1
    _reset_stream_scrubbers(agent)
    original_user_message = (
        persist_user_message if persist_user_message is not None else user_message
    )
    set_current_user_message(user_message)
    should_review_memory = _advance_memory_review_counter(agent)

    messages.append({"role": "user", "content": user_message})
    current_turn_user_idx = len(messages) - 1
    agent._persist_user_message_idx = current_turn_user_idx
    _print_turn_start(agent, user_message)

    if agent._cached_system_prompt is None:
        _restore_or_build_system_prompt(agent, system_message, conversation_history)
    active_system_prompt = agent._cached_system_prompt
    messages, active_system_prompt, conversation_history = _preflight_compress(
        agent=agent,
        messages=messages,
        active_system_prompt=active_system_prompt,
        system_message=system_message,
        conversation_history=conversation_history,
        effective_task_id=effective_task_id,
    )
    plugin_user_context = _build_plugin_user_context(
        agent=agent,
        original_user_message=original_user_message,
        messages=messages,
        conversation_history=conversation_history,
    )
    _bind_interrupt_state(agent)
    _notify_memory_turn_start(agent, original_user_message)
    ext_prefetch_cache = _prefetch_external_memory(agent, original_user_message)
    codex_result = _codex_app_server_result(
        agent=agent,
        user_message=user_message,
        original_user_message=original_user_message,
        messages=messages,
        effective_task_id=effective_task_id,
        should_review_memory=should_review_memory,
    )
    return ConversationTurnSetup(
        user_message=user_message,
        persist_user_message=persist_user_message,
        effective_task_id=effective_task_id,
        messages=messages,
        conversation_history=conversation_history,
        original_user_message=original_user_message,
        should_review_memory=should_review_memory,
        active_system_prompt=active_system_prompt,
        current_turn_user_idx=current_turn_user_idx,
        plugin_user_context=plugin_user_context,
        ext_prefetch_cache=ext_prefetch_cache,
        codex_app_server_result=codex_result,
    )


def _set_runtime_model(agent: Any) -> None:
    try:
        set_runtime_main(
            getattr(agent, "provider", "") or "",
            getattr(agent, "model", "") or "",
        )
    except Exception:
        pass


def _reset_turn_counters(agent: Any) -> None:
    agent._invalid_tool_retries = 0
    agent._invalid_json_retries = 0
    agent._empty_content_retries = 0
    agent._incomplete_scratchpad_retries = 0
    agent._codex_incomplete_retries = 0
    agent._thinking_prefill_retries = 0
    agent._post_tool_empty_retried = False
    agent._last_content_with_tools = None
    agent._last_content_tools_all_housekeeping = False
    agent._mute_post_response = False
    agent._unicode_sanitization_passes = 0
    agent._tool_guardrails.reset_for_turn()
    agent._tool_guardrail_halt_decision = None
    agent._vision_supported = True


def _cleanup_stale_connections(agent: Any) -> None:
    if agent.api_mode == "anthropic_messages":
        return
    try:
        if agent._cleanup_dead_connections():
            agent._emit_status(
                "🔌 Detected stale connections from a previous provider "
                "issue — cleaned up automatically. Proceeding with fresh "
                "connection."
            )
    except Exception:
        pass


def _replay_compression_warning(agent: Any) -> None:
    if agent._compression_warning:
        agent._replay_compression_warning()
        agent._compression_warning = None


def _log_turn_start(
    agent: Any,
    user_message: str,
    conversation_history: List[Dict[str, Any]] | None,
) -> None:
    preview = _summarize_user_message_for_log(user_message)
    msg_preview = (preview[:80] + "...") if len(preview) > 80 else preview
    msg_preview = msg_preview.replace("\n", " ")
    logger.info(
        "conversation turn: session=%s model=%s provider=%s platform=%s history=%d msg=%r",
        agent.session_id or "none",
        agent.model,
        agent.provider or "unknown",
        agent.platform or "unknown",
        len(conversation_history or []),
        msg_preview,
    )


def _hydrate_turn_state(
    agent: Any,
    conversation_history: List[Dict[str, Any]] | None,
) -> None:
    if conversation_history and not agent._todo_store.has_items():
        agent._hydrate_todo_store(conversation_history)
    # Hydrate per-session nudge counters from persisted history so resumed
    # sessions do not postpone memory review indefinitely.
    if conversation_history and agent._user_turn_count == 0:
        prior_user_turns = sum(
            1 for item in conversation_history if item.get("role") == "user"
        )
        if prior_user_turns > 0:
            agent._user_turn_count = prior_user_turns
            if agent._memory_nudge_interval > 0 and agent._turns_since_memory == 0:
                agent._turns_since_memory = prior_user_turns % agent._memory_nudge_interval


def _reset_stream_scrubbers(agent: Any) -> None:
    scrubber = getattr(agent, "_stream_context_scrubber", None)
    if scrubber is not None:
        scrubber.reset()
    think_scrubber = getattr(agent, "_stream_think_scrubber", None)
    if think_scrubber is not None:
        think_scrubber.reset()


def _advance_memory_review_counter(agent: Any) -> bool:
    if not (
        agent._memory_nudge_interval > 0
        and "memory" in agent.valid_tool_names
        and agent._memory_store
    ):
        return False
    agent._turns_since_memory += 1
    if agent._turns_since_memory < agent._memory_nudge_interval:
        return False
    agent._turns_since_memory = 0
    return True


def _print_turn_start(agent: Any, user_message: str) -> None:
    if agent.quiet_mode:
        return
    preview = _summarize_user_message_for_log(user_message)
    suffix = "..." if len(preview) > 60 else ""
    agent._safe_print(f"💬 Starting conversation: '{preview[:60]}{suffix}'")


def _restore_or_build_system_prompt(agent: Any, system_message: str | None, conversation_history: Any) -> None:
    """Restore the cached system prompt from the session DB or build it fresh."""

    stored_prompt = None
    stored_state = "missing"
    if conversation_history and agent._session_db:
        try:
            session_row = agent._session_db.get_session(agent.session_id)
            if session_row is not None:
                raw_prompt = session_row.get("system_prompt")
                if raw_prompt is None:
                    stored_state = "null"
                elif raw_prompt == "":
                    stored_state = "empty"
                else:
                    stored_prompt = raw_prompt
                    stored_state = "present"
        except Exception as exc:
            logger.warning(
                "Session DB get_session failed for system-prompt restore "
                "(session=%s): %s. Falling back to fresh build — prefix "
                "cache will miss for this turn.",
                agent.session_id,
                exc,
            )
    if stored_prompt:
        agent._cached_system_prompt = stored_prompt
        return
    if conversation_history and stored_state in ("null", "empty"):
        logger.warning(
            "Stored system prompt for session %s is %s; rebuilding "
            "from scratch this turn. Prefix cache will miss until "
            "the rebuild persists. Investigate the previous turn's "
            "update_system_prompt write path.",
            agent.session_id,
            stored_state,
        )
    agent._cached_system_prompt = agent._build_system_prompt(system_message)
    _fire_session_start_hook(agent)
    if agent._session_db:
        try:
            agent._session_db.update_system_prompt(
                agent.session_id, agent._cached_system_prompt
            )
        except Exception as exc:
            logger.warning(
                "Session DB update_system_prompt failed for session %s: "
                "%s. Subsequent turns will rebuild the system prompt and "
                "miss the prefix cache.",
                agent.session_id,
                exc,
            )


def _fire_session_start_hook(agent: Any) -> None:
    try:
        from miho_cli.plugins import invoke_hook as _invoke_hook

        _invoke_hook(
            "on_session_start",
            session_id=agent.session_id,
            model=agent.model,
            platform=getattr(agent, "platform", None) or "",
        )
    except Exception as exc:
        logger.warning("on_session_start hook failed: %s", exc)


def _preflight_compress(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    active_system_prompt: str | None,
    system_message: str | None,
    conversation_history: List[Dict[str, Any]] | None,
    effective_task_id: str,
) -> tuple[List[Dict[str, Any]], str | None, List[Dict[str, Any]] | None]:
    if not (
        agent.compression_enabled
        and len(messages)
        > agent.context_compressor.protect_first_n
        + agent.context_compressor.protect_last_n
        + 1
    ):
        return messages, active_system_prompt, conversation_history
    preflight_tokens = estimate_request_tokens_rough(
        messages,
        system_prompt=active_system_prompt or "",
        tools=agent.tools or None,
    )
    if preflight_tokens < agent.context_compressor.threshold_tokens:
        return messages, active_system_prompt, conversation_history
    logger.info(
        "Preflight compression: ~%s tokens >= %s threshold (model %s, ctx %s)",
        f"{preflight_tokens:,}",
        f"{agent.context_compressor.threshold_tokens:,}",
        agent.model,
        f"{agent.context_compressor.context_length:,}",
    )
    agent._emit_status(
        "💬 대화가 길어져서 지금까지 내용을 정리하고 있어요. "
        "원활한 진행을 위한 거니 잠깐만 기다려줘!"
    )
    for _ in range(3):
        orig_len = len(messages)
        messages, active_system_prompt = agent._compress_context(
            messages,
            system_message,
            approx_tokens=preflight_tokens,
            task_id=effective_task_id,
        )
        if len(messages) >= orig_len:
            break
        conversation_history = None
        agent._empty_content_retries = 0
        agent._thinking_prefill_retries = 0
        agent._last_content_with_tools = None
        agent._last_content_tools_all_housekeeping = False
        agent._mute_post_response = False
        preflight_tokens = estimate_request_tokens_rough(
            messages,
            system_prompt=active_system_prompt or "",
            tools=agent.tools or None,
        )
        if preflight_tokens < agent.context_compressor.threshold_tokens:
            break
    return messages, active_system_prompt, conversation_history


def _build_plugin_user_context(
    *,
    agent: Any,
    original_user_message: str,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
) -> str:
    plugin_user_context = ""
    try:
        from miho_cli.plugins import invoke_hook as _invoke_hook

        pre_results = _invoke_hook(
            "pre_llm_call",
            session_id=agent.session_id,
            user_message=original_user_message,
            conversation_history=list(messages),
            is_first_turn=(not bool(conversation_history)),
            model=agent.model,
            platform=getattr(agent, "platform", None) or "",
            sender_id=getattr(agent, "_user_id", None) or "",
        )
        ctx_parts: list[str] = []
        for item in pre_results:
            if isinstance(item, dict) and item.get("context"):
                ctx_parts.append(str(item["context"]))
            elif isinstance(item, str) and item.strip():
                ctx_parts.append(item)
        if ctx_parts:
            plugin_user_context = "\n\n".join(ctx_parts)
    except Exception as exc:
        logger.warning("pre_llm_call hook failed: %s", exc)
    pinned_context = build_context_hooks_prompt(original_user_message)
    if pinned_context:
        plugin_user_context = (
            (plugin_user_context + "\n\n") if plugin_user_context else ""
        ) + pinned_context
    return plugin_user_context


def _bind_interrupt_state(agent: Any) -> None:
    agent._turn_failed_file_mutations: Dict[str, Dict[str, Any]] = {}
    agent._execution_thread_id = threading.current_thread().ident
    _ra()._set_interrupt(False, agent._execution_thread_id)
    if agent._interrupt_requested:
        _ra()._set_interrupt(True, agent._execution_thread_id)
        agent._interrupt_thread_signal_pending = False
    else:
        agent._interrupt_message = None
        agent._interrupt_thread_signal_pending = False


def _notify_memory_turn_start(agent: Any, original_user_message: str) -> None:
    if not agent._memory_manager:
        return
    try:
        turn_msg = original_user_message if isinstance(original_user_message, str) else ""
        agent._memory_manager.on_turn_start(agent._user_turn_count, turn_msg)
    except Exception:
        pass


def _prefetch_external_memory(agent: Any, original_user_message: str) -> str:
    if not agent._memory_manager:
        return ""
    try:
        query = original_user_message if isinstance(original_user_message, str) else ""
        return agent._memory_manager.prefetch_all(query) or ""
    except Exception:
        return ""


def _codex_app_server_result(
    *,
    agent: Any,
    user_message: str,
    original_user_message: str,
    messages: List[Dict[str, Any]],
    effective_task_id: str,
    should_review_memory: bool,
) -> Dict[str, Any] | None:
    if agent.api_mode != "codex_app_server":
        return None
    return agent._run_codex_app_server_turn(
        user_message=user_message,
        original_user_message=original_user_message,
        messages=messages,
        effective_task_id=effective_task_id,
        should_review_memory=should_review_memory,
    )


def _ra():
    import run_agent

    return run_agent
