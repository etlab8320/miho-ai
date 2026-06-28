"""Response validation and malformed-response retry handling."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResponseValidationResult:
    action: str
    retry_count: int
    compression_attempts: int
    primary_recovery_attempted: bool
    thinking_spinner: Any | None
    return_value: Dict[str, Any] | None = None


def handle_response_validation(
    *,
    agent: Any,
    response: Any,
    thinking_spinner: Any | None,
    retry_count: int,
    max_retries: int,
    compression_attempts: int,
    primary_recovery_attempted: bool,
    api_duration: float,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
    backoff_fn: Callable[..., float],
    time_module: Any,
) -> ResponseValidationResult:
    """Validate a provider response and decide how the retry loop proceeds."""

    response_invalid, error_details = _validate_response(agent, response)
    if not response_invalid:
        return ResponseValidationResult(
            action="proceed",
            retry_count=retry_count,
            compression_attempts=compression_attempts,
            primary_recovery_attempted=primary_recovery_attempted,
            thinking_spinner=thinking_spinner,
        )

    thinking_spinner = _stop_thinking(agent, thinking_spinner)
    retry_count += 1

    if agent._fallback_index < len(agent._fallback_chain):
        agent._emit_status("⚠️ Empty/malformed response — switching to fallback...")
    if agent._try_activate_fallback():
        return ResponseValidationResult(
            action="continue",
            retry_count=0,
            compression_attempts=0,
            primary_recovery_attempted=False,
            thinking_spinner=thinking_spinner,
        )

    error_msg, provider_name = _extract_invalid_response_details(agent, response)
    failure_hint = _failure_hint(response=response, api_duration=api_duration)
    _log_invalid_response(
        agent=agent,
        error_details=error_details,
        retry_count=retry_count,
        max_retries=max_retries,
        provider_name=provider_name,
        error_msg=error_msg,
        failure_hint=failure_hint,
    )

    if retry_count >= max_retries:
        return _invalid_response_exhausted(
            agent=agent,
            messages=messages,
            conversation_history=conversation_history,
            api_call_count=api_call_count,
            max_retries=max_retries,
            failure_hint=failure_hint,
            retry_count=retry_count,
            compression_attempts=compression_attempts,
            primary_recovery_attempted=primary_recovery_attempted,
            thinking_spinner=thinking_spinner,
        )

    return _wait_before_invalid_response_retry(
        agent=agent,
        messages=messages,
        conversation_history=conversation_history,
        api_call_count=api_call_count,
        retry_count=retry_count,
        max_retries=max_retries,
        compression_attempts=compression_attempts,
        primary_recovery_attempted=primary_recovery_attempted,
        thinking_spinner=thinking_spinner,
        error_details=error_details,
        provider_name=provider_name,
        failure_hint=failure_hint,
        backoff_fn=backoff_fn,
        time_module=time_module,
    )


def _validate_response(agent: Any, response: Any) -> tuple[bool, List[str]]:
    error_details: List[str] = []
    if agent.api_mode == "codex_responses":
        invalid = _validate_codex_response(agent, response, error_details)
    elif agent.api_mode == "anthropic_messages":
        invalid = _validate_basic_transport_response(
            agent, response, error_details, "response.content invalid (not a non-empty list)"
        )
    elif agent.api_mode == "bedrock_converse":
        invalid = _validate_basic_transport_response(
            agent, response, error_details, "Bedrock response invalid (no output or choices)"
        )
    else:
        invalid = _validate_chat_response(agent, response, error_details)
    return invalid, error_details


def _validate_codex_response(
    agent: Any,
    response: Any,
    error_details: List[str],
) -> bool:
    if agent._get_transport().validate_response(response):
        return False
    if response is None:
        error_details.append("response is None")
        return True

    status = str(getattr(response, "status", "") or "").strip().lower()
    if status in {"failed", "cancelled"}:
        error_obj = getattr(response, "error", None)
        error_msg = (
            error_obj.get("message")
            if isinstance(error_obj, dict)
            else str(error_obj)
            if error_obj
            else f"Responses API returned status '{status}'"
        )
        logger.warning(
            "Codex response status='%s' (error=%s). Routing to fallback. %s",
            status,
            error_msg,
            agent._client_log_context(),
        )
        error_details.append(f"response.status={status}: {error_msg}")
        return True

    output_text = getattr(response, "output_text", None)
    output_text_stripped = output_text.strip() if isinstance(output_text, str) else ""
    if output_text_stripped:
        logger.debug(
            "Codex response.output is empty but output_text is present (%d chars); "
            "deferring to normalization.",
            len(output_text_stripped),
        )
        return False

    logger.warning(
        "Codex response.output is empty after stream backfill "
        "(status=%s, incomplete_details=%s, model=%s). api_mode=%s provider=%s",
        getattr(response, "status", None),
        getattr(response, "incomplete_details", None),
        getattr(response, "model", None),
        agent.api_mode,
        agent.provider,
    )
    error_details.append("response.output is empty")
    return True


def _validate_basic_transport_response(
    agent: Any,
    response: Any,
    error_details: List[str],
    invalid_detail: str,
) -> bool:
    if agent._get_transport().validate_response(response):
        return False
    error_details.append("response is None" if response is None else invalid_detail)
    return True


def _validate_chat_response(agent: Any, response: Any, error_details: List[str]) -> bool:
    if agent._get_transport().validate_response(response):
        return False
    if response is None:
        error_details.append("response is None")
    elif not hasattr(response, "choices"):
        error_details.append("response has no 'choices' attribute")
    elif response.choices is None:
        error_details.append("response.choices is None")
    else:
        error_details.append("response.choices is empty")
    return True


def _stop_thinking(agent: Any, thinking_spinner: Any | None) -> Any | None:
    if thinking_spinner:
        thinking_spinner.stop("(´;ω;`) oops, retrying...")
    if agent.thinking_callback:
        agent.thinking_callback("")
    return None


def _extract_invalid_response_details(agent: Any, response: Any) -> tuple[str, str]:
    error_msg = "Unknown"
    provider_name = "Unknown"
    if response and hasattr(response, "error") and response.error:
        error_msg = str(response.error)
        if hasattr(response.error, "metadata") and response.error.metadata:
            provider_name = response.error.metadata.get("provider_name", "Unknown")
    elif response and hasattr(response, "message") and response.message:
        error_msg = str(response.message)
    if provider_name == "Unknown" and response and getattr(response, "model", None):
        provider_name = f"model={response.model}"
    if provider_name == "Unknown" and response and agent.verbose_logging:
        attrs = {k: str(v)[:100] for k, v in vars(response).items() if not k.startswith("_")}
        logging.debug("Response attributes for invalid response: %s", attrs)
    return error_msg, provider_name


def _failure_hint(*, response: Any, api_duration: float) -> str:
    error_code = _response_error_code(response)
    if error_code == 524:
        return f"upstream provider timed out (Cloudflare 524, {api_duration:.0f}s)"
    if error_code == 504:
        return f"upstream gateway timeout (504, {api_duration:.0f}s)"
    if error_code == 429:
        return "rate limited by upstream provider (429)"
    if error_code in {500, 502}:
        return f"upstream server error ({error_code}, {api_duration:.0f}s)"
    if error_code in {503, 529}:
        return f"upstream provider overloaded ({error_code})"
    if error_code is not None:
        return f"upstream error (code {error_code}, {api_duration:.0f}s)"
    if api_duration < 10:
        return f"fast response ({api_duration:.1f}s) — likely rate limited"
    if api_duration > 60:
        return f"slow response ({api_duration:.0f}s) — likely upstream timeout"
    return f"response time {api_duration:.1f}s"


def _response_error_code(response: Any) -> int | None:
    if not (response and hasattr(response, "error") and response.error):
        return None
    raw = getattr(response.error, "code", None)
    if raw is None and isinstance(response.error, dict):
        raw = response.error.get("code")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _log_invalid_response(
    *,
    agent: Any,
    error_details: List[str],
    retry_count: int,
    max_retries: int,
    provider_name: str,
    error_msg: str,
    failure_hint: str,
) -> None:
    agent._vprint(
        f"{agent.log_prefix}⚠️  Invalid API response "
        f"(attempt {retry_count}/{max_retries}): {', '.join(error_details)}",
        force=True,
    )
    agent._vprint(f"{agent.log_prefix}   🏢 Provider: {provider_name}", force=True)
    agent._vprint(
        f"{agent.log_prefix}   📝 Provider message: {agent._clean_error_message(error_msg)}",
        force=True,
    )
    agent._vprint(f"{agent.log_prefix}   ⏱️  {failure_hint}", force=True)


def _invalid_response_exhausted(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
    max_retries: int,
    failure_hint: str,
    retry_count: int,
    compression_attempts: int,
    primary_recovery_attempted: bool,
    thinking_spinner: Any | None,
) -> ResponseValidationResult:
    agent._emit_status(f"⚠️ Max retries ({max_retries}) for invalid responses — trying fallback...")
    if agent._try_activate_fallback():
        return ResponseValidationResult("continue", 0, 0, False, thinking_spinner)
    agent._emit_status(f"❌ Max retries ({max_retries}) exceeded for invalid responses. Giving up.")
    logger.error("%sInvalid API response after %s retries.", agent.log_prefix, max_retries)
    agent._persist_session(messages, conversation_history)
    return ResponseValidationResult(
        action="return",
        retry_count=retry_count,
        compression_attempts=compression_attempts,
        primary_recovery_attempted=primary_recovery_attempted,
        thinking_spinner=thinking_spinner,
        return_value={
            "messages": messages,
            "completed": False,
            "api_calls": api_call_count,
            "error": f"Invalid API response after {max_retries} retries: {failure_hint}",
            "failed": True,
        },
    )


def _wait_before_invalid_response_retry(
    *,
    agent: Any,
    messages: List[Dict[str, Any]],
    conversation_history: List[Dict[str, Any]] | None,
    api_call_count: int,
    retry_count: int,
    max_retries: int,
    compression_attempts: int,
    primary_recovery_attempted: bool,
    thinking_spinner: Any | None,
    error_details: List[str],
    provider_name: str,
    failure_hint: str,
    backoff_fn: Callable[..., float],
    time_module: Any,
) -> ResponseValidationResult:
    wait_time = backoff_fn(retry_count, base_delay=5.0, max_delay=120.0)
    agent._vprint(
        f"{agent.log_prefix}⏳ Retrying in {wait_time:.1f}s ({failure_hint})...",
        force=True,
    )
    logger.warning(
        "Invalid API response (retry %s/%s): %s | Provider: %s",
        retry_count,
        max_retries,
        ", ".join(error_details),
        provider_name,
    )
    sleep_end = time_module.time() + wait_time
    backoff_touch_counter = 0
    while time_module.time() < sleep_end:
        if agent._interrupt_requested:
            agent._vprint(
                f"{agent.log_prefix}⚡ Interrupt detected during retry wait, aborting.",
                force=True,
            )
            agent._persist_session(messages, conversation_history)
            agent.clear_interrupt()
            return ResponseValidationResult(
                action="return",
                retry_count=retry_count,
                compression_attempts=compression_attempts,
                primary_recovery_attempted=primary_recovery_attempted,
                thinking_spinner=thinking_spinner,
                return_value={
                    "final_response": (
                        f"Operation interrupted during retry ({failure_hint}, "
                        f"attempt {retry_count}/{max_retries})."
                    ),
                    "messages": messages,
                    "api_calls": api_call_count,
                    "completed": False,
                    "interrupted": True,
                },
            )
        time_module.sleep(0.2)
        backoff_touch_counter += 1
        if backoff_touch_counter % 150 == 0:
            agent._touch_activity(
                f"retry backoff ({retry_count}/{max_retries}), "
                f"{int(sleep_end - time_module.time())}s remaining"
            )
    return ResponseValidationResult(
        action="continue",
        retry_count=retry_count,
        compression_attempts=compression_attempts,
        primary_recovery_attempted=primary_recovery_attempted,
        thinking_spinner=thinking_spinner,
    )
