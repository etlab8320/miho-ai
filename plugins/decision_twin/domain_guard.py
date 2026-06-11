"""Negative safety guards for impossible cross-domain LLM routes."""

from __future__ import annotations

from typing import Any

from .contracts import decision_tool_contracts
from .router import LlmRouteDecision


_HAKJONG_MARKERS = (
    "학종",
    "학생부종합",
    "premium_hakjong_report",
    "hakjong",
)
_LIFE_RECORD_MARKERS = (
    "생기부",
    "생활기록부",
    "학교생활기록부",
    "life_record",
)
_JUNGSI_DOMAIN = "jungsi_excel_importer"
_JUNGSI_PREFIX = "jungsi_"


def has_domain_conflict(
    decision: LlmRouteDecision,
    *,
    user_text: str,
    owner_context: str = "",
    turn_context: dict[str, Any] | None = None,
) -> bool:
    """Return True when the selected tool conflicts with protected context.

    This is a negative guard, not keyword routing: it never chooses a tool. It
    only blocks high-risk domain swaps after the LLM has already proposed one.
    """
    tool = decision.required_tool
    if not tool:
        return False
    if _tool_domain(tool) != _JUNGSI_DOMAIN:
        return False
    context = _context_blob(user_text, owner_context, turn_context)
    return _contains_any(context, _HAKJONG_MARKERS) or _contains_any(context, _LIFE_RECORD_MARKERS)


def _tool_domain(tool: str) -> str:
    contract = decision_tool_contracts().get(tool, {})
    domain = str(contract.get("domain") or "")
    if domain:
        return domain
    if tool.startswith(_JUNGSI_PREFIX):
        return _JUNGSI_DOMAIN
    return ""


def _context_blob(user_text: str, owner_context: str, turn_context: dict[str, Any] | None) -> str:
    values = [user_text, owner_context]
    if isinstance(turn_context, dict):
        values.extend(str(value) for value in turn_context.values())
    return "\n".join(str(value or "") for value in values).casefold()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker.casefold() in text for marker in markers)
