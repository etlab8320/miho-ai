"""Max-retry and backoff helpers for API-error recovery."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MaxRetryResult:
    action: str
    return_value: Dict[str, Any] | None = None


def handle_max_retries(
    *,
    agent: Any,
    api_error: Exception,
    error_msg: str,
    error_summary: str,
    is_rate_limited: bool,
    provider: str,
    model: str,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
    api_messages: List[Dict[str, Any]],
    api_kwargs: Dict[str, Any] | None,
    approx_tokens: int,
    retry_count: int,
    max_retries: int,
    primary_recovery_attempted: bool,
) -> MaxRetryResult:
    if not primary_recovery_attempted and agent._try_recover_primary_transport(
        api_error,
        retry_count=retry_count,
        max_retries=max_retries,
    ):
        return MaxRetryResult("continue")
    agent._emit_status(f"⚠️ Max retries ({max_retries}) exhausted — trying fallback...")
    if agent._try_activate_fallback():
        return MaxRetryResult("fallback")
    agent._emit_status(
        f"❌ {'Rate limited' if is_rate_limited else 'API failed'} after "
        f"{max_retries} retries — {error_summary}"
    )
    agent._vprint(f"{agent.log_prefix}   💀 Final error: {error_summary}", force=True)
    stream_drop = _is_stream_drop(api_error, error_msg)
    if stream_drop:
        _print_stream_drop_hint(agent)
    logger.error(
        "%sAPI call failed after %s retries. %s | provider=%s model=%s msgs=%s tokens=~%s",
        agent.log_prefix,
        max_retries,
        error_summary,
        provider,
        model,
        len(api_messages),
        f"{approx_tokens:,}",
    )
    if api_kwargs is not None:
        agent._dump_api_request_debug(
            api_kwargs,
            reason="max_retries_exhausted",
            error=api_error,
        )
    agent._persist_session(messages, conversation_history)
    final_response = f"API call failed after {max_retries} retries: {error_summary}"
    if stream_drop:
        final_response += (
            "\n\nThe provider's stream connection keeps dropping — this often happens "
            "when generating very large tool call responses (e.g. write_file with "
            "long content). Try asking me to use execute_code with Python's open() "
            "for large files, or to write in smaller sections."
        )
    return MaxRetryResult(
        "return",
        {
            "final_response": final_response,
            "messages": messages,
            "api_calls": api_call_count,
            "completed": False,
            "failed": True,
            "error": error_summary,
        },
    )


def wait_before_retry(
    *,
    agent: Any,
    api_error: Exception,
    is_rate_limited: bool,
    retry_count: int,
    max_retries: int,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
    backoff_fn: Callable[..., float],
    time_module: Any,
) -> Dict[str, Any] | None:
    retry_after = _retry_after_seconds(api_error) if is_rate_limited else None
    wait_time = retry_after if retry_after else backoff_fn(
        retry_count,
        base_delay=2.0,
        max_delay=60.0,
    )
    if is_rate_limited:
        agent._emit_status(
            f"⏱️ Rate limited. Waiting {wait_time:.1f}s "
            f"(attempt {retry_count + 1}/{max_retries})..."
        )
    else:
        agent._emit_status(
            f"⏳ Retrying in {wait_time:.1f}s "
            f"(attempt {retry_count}/{max_retries})..."
        )
    logger.warning(
        "Retrying API call in %ss (attempt %s/%s) %s error=%s",
        wait_time,
        retry_count,
        max_retries,
        agent._client_log_context(),
        api_error,
    )
    sleep_end = time_module.time() + wait_time
    touch_counter = 0
    while time_module.time() < sleep_end:
        if agent._interrupt_requested:
            agent._vprint(
                f"{agent.log_prefix}⚡ Interrupt detected during retry wait, aborting.",
                force=True,
            )
            agent._persist_session(messages, conversation_history)
            agent.clear_interrupt()
            return {
                "final_response": (
                    "Operation interrupted: retrying API call after error "
                    f"(retry {retry_count}/{max_retries})."
                ),
                "messages": messages,
                "api_calls": api_call_count,
                "completed": False,
                "interrupted": True,
            }
        time_module.sleep(0.2)
        touch_counter += 1
        if touch_counter % 150 == 0:
            agent._touch_activity(
                f"error retry backoff ({retry_count}/{max_retries}), "
                f"{int(sleep_end - time_module.time())}s remaining"
            )
    return None


def _is_stream_drop(api_error: Exception, error_msg: str) -> bool:
    return not getattr(api_error, "status_code", None) and any(
        part in error_msg
        for part in (
            "connection lost",
            "connection reset",
            "connection closed",
            "network connection",
            "network error",
            "terminated",
        )
    )


def _print_stream_drop_hint(agent: Any) -> None:
    agent._vprint(
        f"{agent.log_prefix}   💡 The provider's stream connection keeps dropping. "
        "This often happens when the model tries to write a very large file "
        "in a single tool call.",
        force=True,
    )
    agent._vprint(
        f"{agent.log_prefix}      Try asking the model to use execute_code with "
        "Python's open() for large files, or to write the file in smaller sections.",
        force=True,
    )


def _retry_after_seconds(api_error: Exception) -> float | None:
    headers = getattr(getattr(api_error, "response", None), "headers", None)
    if not (headers and hasattr(headers, "get")):
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if not raw:
        return None
    try:
        return min(float(raw), 120)
    except (TypeError, ValueError):
        return None
