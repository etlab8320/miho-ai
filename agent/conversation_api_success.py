"""Successful API-call accounting for the conversation loop."""

from __future__ import annotations

import logging
from typing import Any

from agent.model_metadata import save_context_length
from agent.nous_rate_guard import clear_nous_rate_limit
from agent.usage_pricing import estimate_usage_cost, normalize_usage

logger = logging.getLogger(__name__)


def record_successful_api_call(*, agent: Any, response: Any, api_duration: float) -> None:
    """Update usage, cost, cache, and rate-limit state after a successful call."""

    _record_token_usage(agent=agent, response=response, api_duration=api_duration)
    if agent.provider == "nous":
        try:
            clear_nous_rate_limit()
        except Exception:
            pass


def _record_token_usage(*, agent: Any, response: Any, api_duration: float) -> None:
    if not (hasattr(response, "usage") and response.usage):
        return

    canonical_usage = normalize_usage(
        response.usage,
        provider=agent.provider,
        api_mode=agent.api_mode,
    )
    prompt_tokens = canonical_usage.prompt_tokens
    completion_tokens = canonical_usage.output_tokens
    total_tokens = canonical_usage.total_tokens
    usage_dict = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }
    agent.context_compressor.update_from_response(usage_dict)
    _cache_context_probe(agent)
    _add_session_usage(agent, canonical_usage)
    _log_usage_call(
        agent=agent,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cache_read_tokens=canonical_usage.cache_read_tokens,
        api_duration=api_duration,
    )
    cost_result = estimate_usage_cost(
        agent.model,
        canonical_usage,
        provider=agent.provider,
        base_url=agent.base_url,
        api_key=getattr(agent, "api_key", ""),
    )
    if cost_result.amount_usd is not None:
        agent.session_estimated_cost_usd += float(cost_result.amount_usd)
    agent.session_cost_status = cost_result.status
    agent.session_cost_source = cost_result.source
    _persist_token_counts(
        agent=agent,
        canonical_usage=canonical_usage,
        cost_result=cost_result,
        total_tokens=total_tokens,
    )
    if agent.verbose_logging:
        logging.debug(
            "Token usage: prompt=%s, completion=%s, total=%s",
            f"{usage_dict['prompt_tokens']:,}",
            f"{usage_dict['completion_tokens']:,}",
            f"{usage_dict['total_tokens']:,}",
        )
    _surface_cache_hit_stats(agent=agent, canonical_usage=canonical_usage, prompt_tokens=prompt_tokens)


def _cache_context_probe(agent: Any) -> None:
    compressor = agent.context_compressor
    if not getattr(compressor, "_context_probed", False):
        return
    ctx = compressor.context_length
    if getattr(compressor, "_context_probe_persistable", False):
        save_context_length(agent.model, agent.base_url, ctx)
        agent._safe_print(f"{agent.log_prefix}💾 Cached context length: {ctx:,} tokens for {agent.model}")
    compressor._context_probed = False
    compressor._context_probe_persistable = False


def _add_session_usage(agent: Any, canonical_usage: Any) -> None:
    agent.session_prompt_tokens += canonical_usage.prompt_tokens
    agent.session_completion_tokens += canonical_usage.output_tokens
    agent.session_total_tokens += canonical_usage.total_tokens
    agent.session_api_calls += 1
    agent.session_input_tokens += canonical_usage.input_tokens
    agent.session_output_tokens += canonical_usage.output_tokens
    agent.session_cache_read_tokens += canonical_usage.cache_read_tokens
    agent.session_cache_write_tokens += canonical_usage.cache_write_tokens
    agent.session_reasoning_tokens += canonical_usage.reasoning_tokens


def _log_usage_call(
    *,
    agent: Any,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cache_read_tokens: int,
    api_duration: float,
) -> None:
    cache_pct = ""
    if cache_read_tokens and prompt_tokens:
        cache_pct = f" cache={cache_read_tokens}/{prompt_tokens} ({100 * cache_read_tokens / prompt_tokens:.0f}%)"
    logger.info(
        "API call #%d: model=%s provider=%s in=%d out=%d total=%d latency=%.1fs%s",
        agent.session_api_calls,
        agent.model,
        agent.provider or "unknown",
        prompt_tokens,
        completion_tokens,
        total_tokens,
        api_duration,
        cache_pct,
    )


def _persist_token_counts(
    *,
    agent: Any,
    canonical_usage: Any,
    cost_result: Any,
    total_tokens: int,
) -> None:
    if not (agent._session_db and agent.session_id):
        return
    try:
        if not agent._session_db_created:
            agent._ensure_db_session()
        agent._session_db.update_token_counts(
            agent.session_id,
            input_tokens=canonical_usage.input_tokens,
            output_tokens=canonical_usage.output_tokens,
            cache_read_tokens=canonical_usage.cache_read_tokens,
            cache_write_tokens=canonical_usage.cache_write_tokens,
            reasoning_tokens=canonical_usage.reasoning_tokens,
            estimated_cost_usd=float(cost_result.amount_usd)
            if cost_result.amount_usd is not None
            else None,
            cost_status=cost_result.status,
            cost_source=cost_result.source,
            billing_provider=agent.provider,
            billing_base_url=agent.base_url,
            billing_mode="subscription_included"
            if cost_result.status == "included"
            else None,
            model=agent.model,
            api_call_count=1,
        )
    except Exception as exc:
        logger.debug(
            "Token persistence failed (session=%s, tokens=%d): %s",
            agent.session_id,
            total_tokens,
            exc,
        )


def _surface_cache_hit_stats(
    *,
    agent: Any,
    canonical_usage: Any,
    prompt_tokens: int,
) -> None:
    cached = canonical_usage.cache_read_tokens
    written = canonical_usage.cache_write_tokens
    if not ((cached or written) and not agent.quiet_mode):
        return
    hit_pct = (cached / prompt_tokens * 100) if prompt_tokens > 0 else 0
    agent._vprint(
        f"{agent.log_prefix}   💾 Cache: "
        f"{cached:,}/{prompt_tokens:,} tokens "
        f"({hit_pct:.0f}% hit, {written:,} written)"
    )
