"""One-shot structured API-error recovery paths."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List

from agent.anthropic_adapter import _is_oauth_token
from agent.azure_identity_adapter import is_token_provider
from agent.error_classifier import FailoverReason
from miho_constants import display_miho_home as _dhh_fn
from tools.schema_sanitizer import strip_pattern_and_format

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OneShotRecoveryResult:
    action: str
    recovered_with_pool: bool
    has_retried_429: bool
    image_shrink_retry_attempted: bool
    multimodal_tool_content_retry_attempted: bool
    oauth_1m_beta_retry_attempted: bool
    codex_auth_retry_attempted: bool
    nous_auth_retry_attempted: bool
    copilot_auth_retry_attempted: bool
    anthropic_auth_retry_attempted: bool
    thinking_sig_retry_attempted: bool
    invalid_encrypted_content_retry_attempted: bool
    llama_cpp_grammar_retry_attempted: bool


def handle_one_shot_error_recovery(
    *,
    agent: Any,
    api_error: Exception,
    classified: Any,
    status_code: int | None,
    error_context: Dict[str, Any],
    messages: List[Dict[str, Any]],
    api_messages: List[Dict[str, Any]],
    has_retried_429: bool,
    image_shrink_retry_attempted: bool,
    multimodal_tool_content_retry_attempted: bool,
    oauth_1m_beta_retry_attempted: bool,
    codex_auth_retry_attempted: bool,
    nous_auth_retry_attempted: bool,
    copilot_auth_retry_attempted: bool,
    anthropic_auth_retry_attempted: bool,
    thinking_sig_retry_attempted: bool,
    invalid_encrypted_content_retry_attempted: bool,
    llama_cpp_grammar_retry_attempted: bool,
) -> OneShotRecoveryResult:
    """Run structured one-shot recovery paths before generic retry handling."""

    recovered_with_pool, has_retried_429 = agent._recover_with_credential_pool(
        status_code=status_code,
        has_retried_429=has_retried_429,
        classified_reason=classified.reason,
        error_context=error_context,
    )
    if recovered_with_pool:
        return _result(
            action="continue",
            recovered_with_pool=True,
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

    action, image_shrink_retry_attempted = _try_image_shrink(
        agent, classified, api_messages, image_shrink_retry_attempted
    )
    if action == "continue":
        return _continue_result(locals())

    action, multimodal_tool_content_retry_attempted = _try_multimodal_tool_content(
        agent, classified, api_messages, multimodal_tool_content_retry_attempted
    )
    if action == "continue":
        return _continue_result(locals())

    action, oauth_1m_beta_retry_attempted = _try_oauth_beta(
        agent, classified, oauth_1m_beta_retry_attempted
    )
    if action == "continue":
        return _continue_result(locals())

    action, codex_auth_retry_attempted = _try_codex_auth(
        agent, status_code, codex_auth_retry_attempted
    )
    if action == "continue":
        return _continue_result(locals())

    action, nous_auth_retry_attempted = _try_nous_auth(
        agent, api_error, status_code, nous_auth_retry_attempted
    )
    if action == "continue":
        return _continue_result(locals())

    action, copilot_auth_retry_attempted = _try_copilot_auth(
        agent, status_code, copilot_auth_retry_attempted
    )
    if action == "continue":
        return _continue_result(locals())

    action, anthropic_auth_retry_attempted = _try_anthropic_auth(
        agent, status_code, anthropic_auth_retry_attempted
    )
    if action == "continue":
        return _continue_result(locals())

    action, thinking_sig_retry_attempted = _try_thinking_signature(
        agent, classified, messages, thinking_sig_retry_attempted
    )
    if action == "continue":
        return _continue_result(locals())

    action, invalid_encrypted_content_retry_attempted = _try_encrypted_replay(
        agent, classified, messages, invalid_encrypted_content_retry_attempted
    )
    if action == "continue":
        return _continue_result(locals())

    action, llama_cpp_grammar_retry_attempted = _try_llama_cpp_grammar(
        agent, classified, llama_cpp_grammar_retry_attempted
    )
    return _result(
        action=action,
        recovered_with_pool=False,
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


def _try_image_shrink(agent: Any, classified: Any, api_messages: List[Dict[str, Any]], attempted: bool) -> tuple[str, bool]:
    if classified.reason != FailoverReason.image_too_large or attempted:
        return "proceed", attempted
    attempted = True
    if agent._try_shrink_image_parts_in_messages(api_messages):
        agent._vprint(f"{agent.log_prefix}📐 Image(s) exceeded provider size limit — shrank and retrying...", force=True)
        return "continue", attempted
    logger.info("image-shrink recovery: no data-URL image parts found or shrink didn't reduce size; surfacing original error.")
    return "proceed", attempted


def _try_multimodal_tool_content(agent: Any, classified: Any, api_messages: List[Dict[str, Any]], attempted: bool) -> tuple[str, bool]:
    if classified.reason != FailoverReason.multimodal_tool_content_unsupported or attempted:
        return "proceed", attempted
    attempted = True
    if agent._try_strip_image_parts_from_tool_messages(api_messages):
        agent._vprint(
            f"{agent.log_prefix}📐 Provider rejected list-type tool content — downgraded screenshots to text and retrying...",
            force=True,
        )
        return "continue", attempted
    logger.info("multimodal-tool-content recovery: no list-type tool messages with image parts found; surfacing original error.")
    return "proceed", attempted


def _try_oauth_beta(agent: Any, classified: Any, attempted: bool) -> tuple[str, bool]:
    if not (
        classified.reason == FailoverReason.oauth_long_context_beta_forbidden
        and agent.api_mode == "anthropic_messages"
        and agent._is_anthropic_oauth
        and not attempted
    ):
        return "proceed", attempted
    attempted = True
    if getattr(agent, "_oauth_1m_beta_disabled", False):
        return "proceed", attempted
    agent._oauth_1m_beta_disabled = True
    try:
        agent._anthropic_client.close()
    except Exception:
        pass
    agent._rebuild_anthropic_client()
    agent._vprint(
        f"{agent.log_prefix}🔕 OAuth subscription doesn't support the 1M-context beta — disabled for this session and retrying...",
        force=True,
    )
    return "continue", attempted


def _try_codex_auth(agent: Any, status_code: int | None, attempted: bool) -> tuple[str, bool]:
    if not (
        agent.api_mode == "codex_responses"
        and agent.provider in {"openai-codex", "xai-oauth"}
        and status_code == 401
        and not attempted
    ):
        return "proceed", attempted
    attempted = True
    if agent._try_refresh_codex_client_credentials(force=True):
        label = "xAI OAuth" if agent.provider == "xai-oauth" else "Codex"
        agent._vprint(f"{agent.log_prefix}🔐 {label} auth refreshed after 401. Retrying request...")
        return "continue", attempted
    return "proceed", attempted


def _try_nous_auth(agent: Any, api_error: Exception, status_code: int | None, attempted: bool) -> tuple[str, bool]:
    if not (agent.api_mode == "chat_completions" and agent.provider == "nous" and status_code == 401 and not attempted):
        return "proceed", attempted
    attempted = True
    if agent._try_refresh_nous_client_credentials(force=True):
        print(f"{agent.log_prefix}🔐 Nous agent key refreshed after 401. Retrying request...")
        return "continue", attempted
    _print_nous_auth_diagnostics(agent, api_error)
    return "proceed", attempted


def _try_copilot_auth(agent: Any, status_code: int | None, attempted: bool) -> tuple[str, bool]:
    if not (agent.provider == "copilot" and status_code == 401 and not attempted):
        return "proceed", attempted
    attempted = True
    if agent._try_refresh_copilot_client_credentials():
        agent._vprint(f"{agent.log_prefix}🔐 Copilot credentials refreshed after 401. Retrying request...")
        return "continue", attempted
    return "proceed", attempted


def _try_anthropic_auth(agent: Any, status_code: int | None, attempted: bool) -> tuple[str, bool]:
    if not (
        agent.api_mode == "anthropic_messages"
        and status_code == 401
        and hasattr(agent, "_anthropic_api_key")
        and not attempted
    ):
        return "proceed", attempted
    attempted = True
    if agent._try_refresh_anthropic_client_credentials():
        print(f"{agent.log_prefix}🔐 Anthropic credentials refreshed after 401. Retrying request...")
        return "continue", attempted
    _print_anthropic_auth_diagnostics(agent)
    return "proceed", attempted


def _try_thinking_signature(agent: Any, classified: Any, messages: List[Dict[str, Any]], attempted: bool) -> tuple[str, bool]:
    if classified.reason != FailoverReason.thinking_signature or attempted:
        return "proceed", attempted
    attempted = True
    for msg in messages:
        if isinstance(msg, dict):
            msg.pop("reasoning_details", None)
    agent._vprint(f"{agent.log_prefix}⚠️  Thinking block signature invalid — stripped all thinking blocks, retrying...", force=True)
    logger.warning("%sThinking block signature recovery: stripped reasoning_details from %d messages", agent.log_prefix, len(messages))
    return "continue", attempted


def _try_encrypted_replay(agent: Any, classified: Any, messages: List[Dict[str, Any]], attempted: bool) -> tuple[str, bool]:
    if not (
        classified.reason == FailoverReason.invalid_encrypted_content
        and not attempted
        and agent.api_mode == "codex_responses"
        and bool(getattr(agent, "_codex_reasoning_replay_enabled", True))
        and any(
            isinstance(msg, dict)
            and msg.get("role") == "assistant"
            and isinstance(msg.get("codex_reasoning_items"), list)
            and msg.get("codex_reasoning_items")
            for msg in messages
        )
    ):
        return "proceed", attempted
    attempted = True
    stats = agent._disable_codex_reasoning_replay(messages)
    agent._vprint(
        f"{agent.log_prefix}⚠️  Encrypted reasoning replay was rejected by the provider — "
        f"disabled replay and stripped {stats['items']} item(s) from {stats['messages']} message(s), retrying...",
        force=True,
    )
    logger.warning(
        "%sInvalid encrypted reasoning recovery: disabled replay and stripped %d items from %d messages",
        agent.log_prefix,
        stats["items"],
        stats["messages"],
    )
    return "continue", attempted


def _try_llama_cpp_grammar(agent: Any, classified: Any, attempted: bool) -> tuple[str, bool]:
    if classified.reason != FailoverReason.llama_cpp_grammar_pattern or attempted:
        return "proceed", attempted
    attempted = True
    try:
        _, stripped = strip_pattern_and_format(agent.tools)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("%sllama.cpp grammar recovery: strip helper failed: %s", agent.log_prefix, exc)
        stripped = 0
    if stripped:
        agent._vprint(
            f"{agent.log_prefix}⚠️  llama.cpp rejected tool schema grammar — stripped {stripped} pattern/format keyword(s), retrying...",
            force=True,
        )
        logger.warning("%sllama.cpp grammar recovery: stripped %d pattern/format keyword(s) from tool schemas", agent.log_prefix, stripped)
        return "continue", attempted
    logger.warning("%sllama.cpp grammar error but no pattern/format keywords to strip — falling through to normal retry", agent.log_prefix)
    return "proceed", attempted


def _print_nous_auth_diagnostics(agent: Any, api_error: Exception) -> None:
    home = _dhh_fn()
    body_text = ""
    try:
        body = getattr(api_error, "body", None) or getattr(api_error, "response", None)
        if body is not None:
            body_text = str(body)[:200]
    except Exception:
        pass
    print(f"{agent.log_prefix}🔐 Nous 401 — Portal authentication failed.")
    if body_text:
        print(f"{agent.log_prefix}   Response: {body_text}")
    print(f"{agent.log_prefix}   Most likely: Portal OAuth expired, account out of credits, or agent key revoked.")
    print(f"{agent.log_prefix}   Troubleshooting:")
    print(f"{agent.log_prefix}     • Re-authenticate: miho login --provider nous")
    print(f"{agent.log_prefix}     • Check credits / billing: https://portal.nousresearch.com")
    print(f"{agent.log_prefix}     • Verify stored credentials: {home}/auth.json")
    print(f"{agent.log_prefix}     • Switch providers temporarily: /model <model> --provider openrouter")


def _print_anthropic_auth_diagnostics(agent: Any) -> None:
    key = agent._anthropic_api_key
    home = _dhh_fn()
    print(f"{agent.log_prefix}🔐 Anthropic 401 — authentication failed.")
    if is_token_provider(key):
        print(f"{agent.log_prefix}   Auth method: Microsoft Entra ID (httpx event hook)")
        print(f"{agent.log_prefix}   Run `miho doctor` for credential-chain diagnostics, or")
        print(f"{agent.log_prefix}   `az login` if your developer session expired.")
    else:
        auth_method = "Bearer (OAuth/setup-token)" if _is_oauth_token(key) else "x-api-key (API key)"
        print(f"{agent.log_prefix}   Auth method: {auth_method}")
        print(
            f"{agent.log_prefix}   Token prefix: {key[:12]}..."
            if isinstance(key, str) and len(key) > 12
            else f"{agent.log_prefix}   Token: (empty or short)"
        )
    print(f"{agent.log_prefix}   Troubleshooting:")
    print(f"{agent.log_prefix}     • Check ANTHROPIC_TOKEN in {home}/.env for Miho-managed OAuth/setup tokens")
    print(f"{agent.log_prefix}     • Check ANTHROPIC_API_KEY in {home}/.env for API keys or legacy token values")
    print(f"{agent.log_prefix}     • For API keys: verify at https://platform.claude.com/settings/keys")
    print(f"{agent.log_prefix}     • For Claude Code: run 'claude /login' to refresh, then retry")
    print(f"{agent.log_prefix}     • Legacy cleanup: miho config set ANTHROPIC_TOKEN \"\"")
    print(f"{agent.log_prefix}     • Clear stale keys: miho config set ANTHROPIC_API_KEY \"\"")


def _continue_result(values: Dict[str, Any]) -> OneShotRecoveryResult:
    return _result(action="continue", recovered_with_pool=False, **_flag_values(values))


def _flag_values(values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "has_retried_429": values["has_retried_429"],
        "image_shrink_retry_attempted": values["image_shrink_retry_attempted"],
        "multimodal_tool_content_retry_attempted": values["multimodal_tool_content_retry_attempted"],
        "oauth_1m_beta_retry_attempted": values["oauth_1m_beta_retry_attempted"],
        "codex_auth_retry_attempted": values["codex_auth_retry_attempted"],
        "nous_auth_retry_attempted": values["nous_auth_retry_attempted"],
        "copilot_auth_retry_attempted": values["copilot_auth_retry_attempted"],
        "anthropic_auth_retry_attempted": values["anthropic_auth_retry_attempted"],
        "thinking_sig_retry_attempted": values["thinking_sig_retry_attempted"],
        "invalid_encrypted_content_retry_attempted": values["invalid_encrypted_content_retry_attempted"],
        "llama_cpp_grammar_retry_attempted": values["llama_cpp_grammar_retry_attempted"],
    }


def _result(**kwargs: Any) -> OneShotRecoveryResult:
    return OneShotRecoveryResult(**kwargs)
