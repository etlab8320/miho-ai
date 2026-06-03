"""Semantic fast path for simple student record lookups."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from . import semantic_intents
from .natural_router_payload import load_payload, payload_message, today_kst, tool_timeout_message
from .route_overrides import OUTPUT_INTENT_GROUP, OUTPUT_INTENTS
from .thread_context import remember_thread_context


logger = logging.getLogger(__name__)
ToolHandler = Callable[..., str]

RECORD_INTENT_GROUP = "academy_student_record_fast_path"
RECORD_INTENTS: dict[str, tuple[str, ...]] = {
    "record": (
        "학생 최근 실기 기록 보여줘",
        "학생 측정 기록 불러와줘",
        "학생 수행 기록 알려줘",
        "학생 종목별 최근 기록 보여줘",
        "학생 실기 결과 조회해줘",
    ),
    "none": (
        "학생 출석 기록 보여줘",
        "강사 출근 일정 알려줘",
        "오늘 반배치 보여줘",
        "운동계획서 불러와줘",
        "학원 일정 확인해줘",
    ),
}


async def try_student_record_fast_path(
    text: str,
    *,
    handlers: dict[str, ToolHandler],
    tool_timeout: float,
    today: str | None,
    context_key: str | None,
) -> str | None:
    """Handle plain student record lookups without falling into the body agent."""

    if not _is_plain_record_lookup(text):
        return None
    handler = handlers.get("academy_student_record_lookup")
    if handler is None:
        return None
    args = {
        "student_query": text,
        "event_query": "",
        "date": "",
        "today": today or today_kst(),
        "period_days": 30,
    }
    try:
        raw_result = await asyncio.wait_for(
            asyncio.to_thread(handler, args),
            timeout=tool_timeout,
        )
    except TimeoutError:
        return tool_timeout_message()
    except Exception as exc:
        logger.info("academy student record fast path failed: %s", exc)
        return "학원 데이터를 조회하다가 오류가 났어."
    payload = load_payload(raw_result)
    remember_thread_context(context_key, tool_name="academy_student_record_lookup", args=args, payload=payload)
    return payload_message(payload)


def _is_plain_record_lookup(text: str) -> bool:
    record_label = semantic_intents.classify(
        text,
        RECORD_INTENT_GROUP,
        RECORD_INTENTS,
        negative_label="none",
        min_margin=0.04,
    )
    if record_label != "record":
        return False
    output_label = semantic_intents.classify(
        text,
        OUTPUT_INTENT_GROUP,
        OUTPUT_INTENTS,
        negative_label="none",
        min_margin=0.04,
    )
    return output_label not in {"image", "card"}
