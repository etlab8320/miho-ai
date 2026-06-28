"""Final assistant-output plugin hook runner."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

logger = logging.getLogger(__name__)
HookInvoker = Callable[..., Sequence[Any]]
_GATEWAY_SURFACES = frozenset(
    {
        "api_server",
        "discord",
        "gateway",
        "matrix",
        "mattermost",
        "slack",
        "telegram",
        "webhook",
    }
)


def apply_transform_llm_output_hooks(
    *,
    response_text: str,
    user_message: str,
    conversation_history: list[dict[str, Any]],
    session_id: str,
    model: str,
    platform: str,
    invoke_hook: HookInvoker | None = None,
) -> str:
    """Apply transform_llm_output hooks and keep first non-empty string."""

    final_response = str(response_text or "")
    if not final_response:
        return final_response
    runner = invoke_hook or _default_invoke_hook
    hook_context = {
        "user_message": user_message,
        "conversation_history": list(conversation_history),
        "session_id": session_id or "",
        "model": model,
        "platform": platform or "",
    }
    try:
        transform_results = runner(
            "transform_llm_output",
            response_text=final_response,
            **hook_context,
        )
        for hook_result in transform_results or ():
            if isinstance(hook_result, str) and hook_result:
                return hook_result
    except Exception as exc:
        logger.warning("transform_llm_output hook failed: %s", exc)
        return _recover_gateway_transform_failure(
            final_response=final_response,
            context=hook_context,
        )
    return final_response


def _recover_gateway_transform_failure(
    *,
    final_response: str,
    context: dict[str, Any],
) -> str:
    platform = str(context.get("platform") or "").strip().casefold()
    if platform not in _GATEWAY_SURFACES:
        return final_response
    try:
        from plugins.governance_os import delivery_gate as governance_delivery

        recovered = governance_delivery.governance_transform_llm_output(
            response_text=final_response,
            **context,
        )
    except Exception as exc:
        logger.warning("governance fallback after transform hook failure failed: %s", exc)
        return _safe_gateway_current_result()
    if isinstance(recovered, str) and recovered:
        return recovered
    return _safe_gateway_current_result()


def _safe_gateway_current_result() -> str:
    return "현재 결론: 확정 산출물 없음.\n필요한 입력: 요청을 판단할 원자료."


def _default_invoke_hook(*args: Any, **kwargs: Any) -> Sequence[Any]:
    from miho_cli.plugins import invoke_hook

    return invoke_hook(*args, **kwargs)
