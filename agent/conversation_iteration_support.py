"""Small iteration helpers for the conversation orchestrator."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def consume_iteration_slot(agent: Any) -> bool:
    if agent._budget_grace_call:
        agent._budget_grace_call = False
        return True
    if agent.iteration_budget.consume():
        return True
    if not agent.quiet_mode:
        agent._safe_print(
            f"\n⚠️  Iteration budget exhausted "
            f"({agent.iteration_budget.used}/{agent.iteration_budget.max_total} "
            "iterations used)"
        )
    return False


def refund_api_iteration(agent: Any, api_call_count: int) -> None:
    agent._api_call_count = api_call_count
    try:
        agent.iteration_budget.refund()
    except Exception:
        pass


def fire_step_callback(
    agent: Any,
    api_call_count: int,
    messages: List[Dict[str, Any]],
) -> None:
    if agent.step_callback is None:
        return
    try:
        prev_tools = []
        for idx, message in enumerate(reversed(messages)):
            if message.get("role") != "assistant" or not message.get("tool_calls"):
                continue
            forward_start = len(messages) - idx
            results_by_id = {}
            for tool_message in messages[forward_start:]:
                if tool_message.get("role") != "tool":
                    break
                tool_call_id = tool_message.get("tool_call_id")
                if tool_call_id:
                    results_by_id[tool_call_id] = tool_message.get("content", "")
            prev_tools = [
                {
                    "name": tc["function"]["name"],
                    "result": results_by_id.get(tc.get("id")),
                    "arguments": tc["function"].get("arguments"),
                }
                for tc in message["tool_calls"]
                if isinstance(tc, dict)
            ]
            break
        agent.step_callback(api_call_count, prev_tools)
    except Exception as step_err:
        logger.debug("step_callback error (iteration %s): %s", api_call_count, step_err)


def track_skill_nudge(agent: Any) -> None:
    if agent._skill_nudge_interval > 0 and "skill_manage" in agent.valid_tool_names:
        agent._iters_since_skill += 1


def log_api_request(
    agent: Any,
    messages: List[Dict[str, Any]],
    approx_tokens: int,
) -> None:
    if not agent.verbose_logging:
        return
    logging.debug(
        "API Request - Model: %s, Messages: %s, Tools: %s",
        agent.model,
        len(messages),
        len(agent.tools) if agent.tools else 0,
    )
    logging.debug("Last message role: %s", messages[-1]["role"] if messages else "none")
    logging.debug("Total message size: ~%s tokens", f"{approx_tokens:,}")


def boost_length_continuation_budget(agent: Any, length_continue_retries: int) -> None:
    boost_base = agent.max_tokens if agent.max_tokens else 4096
    boost = boost_base * (length_continue_retries + 1)
    agent._ephemeral_max_output_tokens = min(boost, 32768)
