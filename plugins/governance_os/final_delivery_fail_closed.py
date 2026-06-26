"""Fail-closed recovery for blocked final delivery."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .delivery_safety import contains_internal_guard_leak
from .final_qa import repair_answer_until_pass

FAIL_CLOSED_MESSAGE = (
    "확정 검수 전이라 이 결과는 보내지 않았습니다. 같은 요청을 다시 보내면 검수부터 다시 진행하겠습니다."
)


def recover_blocked_delivery(
    *,
    question: str,
    answer: str,
    evidence: dict[str, Any],
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], str] | None = None,
) -> str:
    repaired = repair_answer_until_pass(
        question,
        answer,
        evidence={**evidence, "fail_closed_recovery": True},
        call_llm=call_llm,
        extract_content=extract_content,
    ).strip()
    original = str(answer or "").strip()
    if repaired and repaired != original and not contains_internal_guard_leak(repaired):
        return repaired
    return FAIL_CLOSED_MESSAGE
