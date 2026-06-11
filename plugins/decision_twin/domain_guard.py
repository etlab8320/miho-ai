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
_MEDIA_DELIVERY_MARKERS = (
    "media:",
    "첨부",
    "전달",
    "다시 줘",
    "다시 보내",
    "파일을 줘",
    "파일 보내",
    "pdf 보내",
    "리포트 파일",
)
_HAKJONG_NEGATION_MARKERS = (
    "학종말고",
    "학종 말고",
    "학생부종합 말고",
)
_SUSI_MARKERS = (
    "수시",
    "교과",
    "실기",
    "내신",
    "체대",
    "체육",
)
_SUSI_SCORE_MARKERS = (
    "내신환산",
    "환산점수",
    "학생 점수",
    "점수로",
)
_SUSI_CUTOFF_MARKERS = (
    "작년 합격자",
    "전년도",
    "전년",
    "컷",
    "입결",
    "최초합",
    "최종합",
)
_RECOMMENDATION_MARKERS = (
    "붙을만한",
    "추천",
    "뽑아",
    "목록",
    "리스트",
    "선별",
    "유리한",
    "할만한",
    "상향",
    "중립",
    "안전",
)
_SCORE_CALCULATION_MARKERS = (
    "계산",
    "환산",
    "검증",
    "맞아",
    "높게",
    "반영식",
)
_JUNGSI_SCORE_TOOLS = (
    "jungsi_student_score_lookup",
    "jungsi_student_university_score",
    "jungsi_cutoff_lookup",
    "jungsi_rule_summary",
    "jungsi_university_search",
)
_LIFE_RECORD_DOMAIN = "life_record"
_JUNGSI_DOMAIN = "jungsi_excel_importer"
_JUNGSI_PREFIX = "jungsi_"
_LIFE_RECORD_PREFIX = "life_record_"


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
    domain = _tool_domain(tool)
    context = _context_blob(user_text, owner_context, turn_context)
    if _is_jungsi_tool(tool, domain):
        if _is_jungsi_score_tool(tool) and _is_score_calculation_context(context):
            return False
        return (
            _contains_any(context, _HAKJONG_MARKERS)
            or _contains_any(context, _LIFE_RECORD_MARKERS)
            or _is_media_delivery_context(context)
        )
    if _is_life_record_tool(tool, domain):
        return _is_susi_score_recommendation_context(context)
    return False


def should_skip_clarify_response(
    *,
    user_text: str,
    owner_context: str = "",
    turn_context: dict[str, Any] | None = None,
) -> bool:
    """Return True when clarification would block a complete score request."""
    current = str(user_text or "").casefold()
    context = _context_blob(user_text, owner_context, turn_context)
    return _is_complete_score_recommendation_context(current) or (
        _contains_any(current, _SUSI_MARKERS)
        and _is_complete_score_recommendation_context(context)
    )


def _tool_domain(tool: str) -> str:
    contract = decision_tool_contracts().get(tool, {})
    domain = str(contract.get("domain") or "")
    if domain:
        return domain
    if tool.startswith(_JUNGSI_PREFIX):
        return _JUNGSI_DOMAIN
    return ""


def _is_jungsi_tool(tool: str, domain: str) -> bool:
    return domain == _JUNGSI_DOMAIN or tool.startswith(_JUNGSI_PREFIX)


def _is_life_record_tool(tool: str, domain: str) -> bool:
    return domain == _LIFE_RECORD_DOMAIN or tool.startswith(_LIFE_RECORD_PREFIX)


def _is_jungsi_score_tool(tool: str) -> bool:
    return tool in _JUNGSI_SCORE_TOOLS


def _is_media_delivery_context(text: str) -> bool:
    return _contains_any(text, _MEDIA_DELIVERY_MARKERS)


def _is_score_calculation_context(text: str) -> bool:
    has_score = _contains_any(text, _SUSI_SCORE_MARKERS) or "점수" in text
    has_calculation = (
        _contains_any(text, _SCORE_CALCULATION_MARKERS)
        or _contains_any(text, _SUSI_CUTOFF_MARKERS)
    )
    return has_score and has_calculation


def _is_susi_score_recommendation_context(text: str) -> bool:
    if _contains_any(text, _HAKJONG_NEGATION_MARKERS):
        return _contains_any(text, _SUSI_SCORE_MARKERS) or _contains_any(text, _SUSI_CUTOFF_MARKERS)
    has_score_basis = _contains_any(text, _SUSI_SCORE_MARKERS) and _contains_any(text, _SUSI_CUTOFF_MARKERS)
    has_susi_scope = _contains_any(text, _SUSI_MARKERS)
    has_recommendation = _contains_any(text, _RECOMMENDATION_MARKERS)
    return has_susi_scope and has_score_basis and has_recommendation


def _is_complete_score_recommendation_context(text: str) -> bool:
    has_student_basis = _contains_any(text, ("성적", "생기부", "학생", "내신"))
    has_score_basis = _contains_any(text, _SUSI_SCORE_MARKERS) or _contains_any(text, _SUSI_CUTOFF_MARKERS)
    has_susi_scope = _contains_any(text, _SUSI_MARKERS)
    has_recommendation = _contains_any(text, _RECOMMENDATION_MARKERS)
    has_count_or_bucket = "6개" in text or _contains_any(text, ("상향", "중립", "안전", "할만한"))
    return has_student_basis and has_score_basis and has_susi_scope and has_recommendation and has_count_or_bucket


def _context_blob(user_text: str, owner_context: str, turn_context: dict[str, Any] | None) -> str:
    values = [user_text, owner_context]
    if isinstance(turn_context, dict):
        values.extend(str(value) for value in turn_context.values())
    return "\n".join(str(value or "") for value in values).casefold()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker.casefold() in text for marker in markers)
