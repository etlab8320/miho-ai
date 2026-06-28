"""Single API attempt execution for the conversation loop."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List
from unittest.mock import Mock

from agent.message_sanitization import _sanitize_structure_non_ascii
from utils import env_var_enabled

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ApiAttemptResult:
    response: Any
    api_kwargs: Dict[str, Any]
    api_duration: float
    thinking_spinner: Any | None


def perform_api_attempt(
    *,
    agent: Any,
    api_messages: List[Dict[str, Any]],
    messages: List[Dict[str, Any]],
    thinking_spinner: Any | None,
    effective_task_id: str,
    original_user_message: str,
    api_call_count: int,
    approx_tokens: int,
    total_chars: int,
) -> ApiAttemptResult:
    """Run one provider API attempt and preserve caller retry semantics."""

    agent._reset_stream_delivery_tracking()
    api_kwargs = agent._build_api_kwargs(api_messages)
    if agent._force_ascii_payload:
        _sanitize_structure_non_ascii(api_kwargs)
    if agent.api_mode == "codex_responses":
        api_kwargs = agent._get_transport().preflight_kwargs(
            api_kwargs, allow_stream=False
        )
    _fire_pre_api_request_hook(
        agent=agent,
        api_kwargs=api_kwargs,
        api_messages=api_messages,
        messages=messages,
        effective_task_id=effective_task_id,
        original_user_message=original_user_message,
        api_call_count=api_call_count,
        approx_tokens=approx_tokens,
        total_chars=total_chars,
    )
    if env_var_enabled("MIHO_DUMP_REQUESTS"):
        agent._dump_api_request_debug(api_kwargs, reason="preflight")
    api_start_time = time.time()
    response, thinking_spinner = _call_provider(
        agent=agent,
        api_kwargs=api_kwargs,
        thinking_spinner=thinking_spinner,
    )
    api_duration = time.time() - api_start_time
    thinking_spinner = _stop_thinking(agent, thinking_spinner)
    if not agent.quiet_mode:
        agent._vprint(f"{agent.log_prefix}⏱️  API call completed in {api_duration:.2f}s")
    if agent.verbose_logging:
        resp_model = getattr(response, "model", "N/A") if response else "N/A"
        usage = response.usage if hasattr(response, "usage") else "N/A"
        logging.debug("API Response received - Model: %s, Usage: %s", resp_model, usage)
    return ApiAttemptResult(
        response=response,
        api_kwargs=api_kwargs,
        api_duration=api_duration,
        thinking_spinner=thinking_spinner,
    )


def _fire_pre_api_request_hook(
    *,
    agent: Any,
    api_kwargs: Dict[str, Any],
    api_messages: List[Dict[str, Any]],
    messages: List[Dict[str, Any]],
    effective_task_id: str,
    original_user_message: str,
    api_call_count: int,
    approx_tokens: int,
    total_chars: int,
) -> None:
    try:
        from miho_cli.plugins import invoke_hook as _invoke_hook

        request_messages = api_kwargs.get("messages")
        if not isinstance(request_messages, list):
            request_messages = api_kwargs.get("input")
        if not isinstance(request_messages, list):
            request_messages = api_messages
        _invoke_hook(
            "pre_api_request",
            task_id=effective_task_id,
            session_id=agent.session_id or "",
            user_message=original_user_message,
            conversation_history=list(messages),
            platform=agent.platform or "",
            model=agent.model,
            provider=agent.provider,
            base_url=agent.base_url,
            api_mode=agent.api_mode,
            api_call_count=api_call_count,
            request_messages=list(request_messages)
            if isinstance(request_messages, list)
            else [],
            message_count=len(api_messages),
            tool_count=len(agent.tools or []),
            approx_input_tokens=approx_tokens,
            request_char_count=total_chars,
            max_tokens=agent.max_tokens,
        )
    except Exception:
        pass


def _call_provider(
    *,
    agent: Any,
    api_kwargs: Dict[str, Any],
    thinking_spinner: Any | None,
) -> tuple[Any, Any | None]:
    def stop_spinner() -> None:
        nonlocal thinking_spinner
        thinking_spinner = _stop_thinking(agent, thinking_spinner)

    if _use_streaming(agent):
        return agent._interruptible_streaming_api_call(
            api_kwargs,
            on_first_delta=stop_spinner,
        ), thinking_spinner
    return agent._interruptible_api_call(api_kwargs), thinking_spinner


def _use_streaming(agent: Any) -> bool:
    if getattr(agent, "_disable_streaming", False):
        return False
    if (
        agent.provider == "copilot-acp"
        or str(agent.base_url or "").lower().startswith("acp://copilot")
        or str(agent.base_url or "").lower().startswith("acp+tcp://")
    ):
        return False
    if not agent._has_stream_consumers() and isinstance(
        getattr(agent, "client", None), Mock
    ):
        return False
    return True


def _stop_thinking(agent: Any, thinking_spinner: Any | None) -> Any | None:
    if thinking_spinner:
        thinking_spinner.stop("")
    if agent.thinking_callback:
        agent.thinking_callback("")
    return None
