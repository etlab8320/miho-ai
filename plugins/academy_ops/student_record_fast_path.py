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
CHART_INTENT_GROUP = "academy_student_record_chart_fast_path"
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
CHART_INTENTS: dict[str, tuple[str, ...]] = {
    "chart": (
        "학생 최근 실기 기록을 그래프 이미지로 보여줘",
        "학생 종목별 기록 추세를 PNG로 그려줘",
        "학생 측정 기록을 회차별 차트로 만들어줘",
        "학생 수행 기록 그래프 이미지를 보내줘",
    ),
    "none": RECORD_INTENTS["none"],
}
SPORTS_MOTION_REPORT_GROUP = "academy_sports_motion_report_exclusion"
SPORTS_MOTION_REPORT_MIN_MARGIN = 0.015
SPORTS_MOTION_REPORT_INTENTS: dict[str, tuple[str, ...]] = {
    "sports_motion_report": (
        "학생 운동퍼포먼스 분석 리포트 만들어줘",
        "학생 운동분석 변인 리포트 만들어줘",
        "MAX 분석 변인으로 운동처방 해줘",
        "점프 분석 리포트 PDF 줘",
        "학생 변인 보고 부족한 점과 운동처방 알려줘",
    ),
    "dual_source_review": (
        "학생 기록과 운동분석을 같이 보고 리포트 만들어줘",
        "최근 기록도 보고 변인도 같이 분석해줘",
        "학생 상태를 기록과 분석 자료 둘 다 보고 판단해줘",
        "Peak 기록과 MAX 운동분석을 비교해서 부족한 점 알려줘",
    ),
    "plain_peak_record": (
        "학생 최근 종목 기록만 보여줘",
        "학생 최근 측정 기록만 알려줘",
        "학생 최근 실기 기록 조회해줘",
        "학생 종목별 최근 기록만 보여줘",
        "학생 최근 기록 목록만 보여줘",
    ),
    "none": RECORD_INTENTS["none"],
}


async def try_student_record_chart_fast_path(
    text: str,
    *,
    handlers: dict[str, ToolHandler],
    tool_timeout: float,
    today: str | None,
    context_key: str | None,
) -> str | None:
    """Handle student record chart image requests without the body agent."""

    handler = handlers.get("academy_student_record_chart_image")
    if handler is None:
        return None
    if _should_defer_record_request_to_body_agent(text):
        return None
    if not _is_record_chart_lookup(text):
        return None
    args = {
        "student_query": text,
        "event_query": "",
        "today": today or today_kst(),
        "period_days": 180,
        "limit": 5,
    }
    try:
        raw_result = await asyncio.wait_for(asyncio.to_thread(handler, args), timeout=tool_timeout)
    except TimeoutError:
        return tool_timeout_message()
    except Exception as exc:
        logger.info("academy student record chart fast path failed: %s", exc)
        return "학원 데이터를 조회하다가 오류가 났어."
    payload = load_payload(raw_result)
    remember_thread_context(context_key, tool_name="academy_student_record_chart_image", args=args, payload=payload)
    return payload_message(payload)


async def try_student_record_fast_path(
    text: str,
    *,
    handlers: dict[str, ToolHandler],
    tool_timeout: float,
    today: str | None,
    context_key: str | None,
) -> str | None:
    """Handle plain student record lookups without falling into the body agent."""

    handler = handlers.get("academy_student_record_lookup")
    if handler is None:
        return None
    if _should_defer_record_request_to_body_agent(text):
        return None
    if not _is_plain_record_lookup(text):
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


def _is_record_chart_lookup(text: str) -> bool:
    chart_label = semantic_intents.classify(
        text,
        CHART_INTENT_GROUP,
        CHART_INTENTS,
        negative_label="none",
        min_margin=0.04,
    )
    if chart_label != "chart":
        return False
    output_label = semantic_intents.classify(
        text,
        OUTPUT_INTENT_GROUP,
        OUTPUT_INTENTS,
        negative_label="none",
        min_margin=0.04,
    )
    return output_label == "image"


def _should_defer_record_request_to_body_agent(text: str) -> bool:
    label = semantic_intents.classify(
        text,
        SPORTS_MOTION_REPORT_GROUP,
        SPORTS_MOTION_REPORT_INTENTS,
        negative_label="plain_peak_record",
        min_margin=SPORTS_MOTION_REPORT_MIN_MARGIN,
    )
    return label in {"sports_motion_report", "dual_source_review"}
