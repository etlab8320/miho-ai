"""LLM response synthesis helpers for academy natural routing."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .commentary_config import (
    COMMENTARY_EXTRA_BODY,
    COMMENTARY_MODEL,
    COMMENTARY_PROVIDER,
)


logger = logging.getLogger(__name__)
ROUTER_TASK = "academy_request_router"
SYNTHESIS_TIMEOUT_SECONDS = 8
POLITE_SUFFIXES = ("예요", "이에요", "습니다", "합니다", "해요", "하세요")


async def synthesize_or_fallback(request: str, payload: dict[str, Any], fallback: str) -> str:
    try:
        text = await asyncio.wait_for(synthesize_response(request, payload), SYNTHESIS_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.info("academy response synthesis skipped: %s", exc)
        return fallback
    return fallback if has_polite_style(text) else text


async def synthesize_response(request: str, payload: dict[str, Any]) -> str:
    from agent.auxiliary_client import async_call_llm

    compact = json.dumps(compact_payload(payload), ensure_ascii=False)
    response = await async_call_llm(
        task=ROUTER_TASK,
        provider=COMMENTARY_PROVIDER,
        model=COMMENTARY_MODEL,
        messages=synthesis_messages(request, {"json": compact}),
        temperature=0.2,
        max_tokens=260,
        timeout=SYNTHESIS_TIMEOUT_SECONDS,
        extra_body=COMMENTARY_EXTRA_BODY,
    )
    text = _response_content(response).strip()
    return text or str(payload.get("message") or "조회 결과를 정리하지 못했어.")


def synthesis_messages(request: str, payload: dict[str, Any]) -> list[dict[str, str]]:
    facts = payload.get("json")
    if not isinstance(facts, str):
        facts = json.dumps(compact_payload(payload), ensure_ascii=False)
    return [
        {
            "role": "system",
            "content": (
                "너는 미호야. 현재 사용자에게 말하듯 자연스러운 한국어 반말로 답해. "
                "능력 있는 오른손처럼 짧고 정확하게 말해. "
                "존대, 보고서 말투, 상담원 말투는 쓰지 마. "
                "학원 운영 데이터는 정확성이 먼저야. "
                "JSON에 없는 사실은 만들지 마. "
                "숫자, 날짜, 학생명, 결석, 지각, 미체크 값은 절대 바꾸지 마. "
                "upcoming 또는 예정 상태는 아직 오지 않은 수업이라 미체크나 문제로 보지 마."
            ),
        },
        {"role": "user", "content": f"요청: {request}\n조회 JSON: {facts}"},
    ]


def compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    keep = {}
    for key in ("operation", "date", "start_date", "end_date", "summary", "message"):
        if key in payload:
            keep[key] = payload[key]
    for key in ("schedules", "consultations", "instructors", "plans", "slots", "absence_dates", "attendance"):
        value = payload.get(key)
        if isinstance(value, list):
            keep[key] = value[:45]
        elif isinstance(value, dict):
            keep[key] = value
    return keep


def has_polite_style(text: str) -> bool:
    compact = text.replace(" ", "")
    return any(suffix in compact for suffix in POLITE_SUFFIXES)


def _response_content(response: Any) -> str:
    try:
        return str(response.choices[0].message.content or "")
    except (AttributeError, IndexError, TypeError):
        return str(response or "")
