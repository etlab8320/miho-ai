"""Pixel document evidence backend plugin."""

from __future__ import annotations

from typing import Any


REVIEWER_INSTRUCTIONS = (
    "문서 근거 reviewer다. 답변이 page_image_path, crop_path, page_number, "
    "source_sha256 근거에 맞는지 확인한다. 표/배점/점수/숫자는 원본 페이지 근거가 "
    "없으면 확정하지 말고 provisional 상태와 재검색 경로를 반환한다."
)


def register(ctx: Any) -> None:
    ctx.register_auxiliary_task(
        key="pixel_document_reviewer",
        display_name="Pixel document reviewer",
        description="Reviews page/crop evidence before document-grounded delivery",
        defaults={
            "provider": "auto",
            "timeout": 90,
            "extra_body": {"reasoning": {"effort": "medium"}},
            "instructions": REVIEWER_INSTRUCTIONS,
        },
    )


__all__ = ["REVIEWER_INSTRUCTIONS", "register"]
