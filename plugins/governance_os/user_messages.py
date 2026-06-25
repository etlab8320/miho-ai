"""User-safe Korean messages for Governance OS delivery fallbacks."""

from __future__ import annotations

SAFE_EVIDENCE_FALLBACK = (
    "확인 근거를 다시 모아 답변을 정리합니다. "
    "확정 점수나 첨부 완료처럼 검증이 필요한 결과는 검증된 값으로만 말하겠습니다."
)

SAFE_INTERNAL_REPAIR_FALLBACK = (
    "확인 근거를 바탕으로 질문에 맞는 답변만 다시 정리합니다. "
    "확정 산출물은 검증된 내용으로만 말하겠습니다."
)
