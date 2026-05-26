"""Shared response guidance for academy tool results."""

from __future__ import annotations

from typing import Any

from .commentary_config import COMMENTARY_MODEL


def academy_response_guidance(*, use_message_as_facts: bool = False) -> dict[str, Any]:
    instruction = (
        "반환된 API 사실만 바탕으로 미호 말투의 짧은 코멘트를 작성해. "
        "없는 사실, 고정 판단, 템플릿 문장을 만들지 마."
    )
    if use_message_as_facts:
        instruction += " message는 사실 요약 원문으로만 참고하고, 그대로 복붙하지 말고 간단히 해석해."
    return {
        "persona_commentary": True,
        "preferred_fast_model": COMMENTARY_MODEL,
        "avoid_hardcoded_judgment": True,
        "instruction": instruction,
    }
