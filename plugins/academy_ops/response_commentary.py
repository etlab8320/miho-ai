"""Optional LLM commentary for fast academy responses."""

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
SUMMARY_COMMENT_TIMEOUT_SECONDS = 4
POLITE_SUFFIXES = ("예요", "이에요", "습니다", "합니다", "해요", "하세요")


async def append_summary_comment_or_fallback(
    request: str,
    compact_payload: dict[str, Any],
    fallback: str,
) -> str:
    try:
        comment = await asyncio.wait_for(
            synthesize_summary_comment(request, compact_payload),
            SUMMARY_COMMENT_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.info("academy summary comment skipped: %s", exc)
        return fallback
    comment = comment.strip()
    if not comment or _has_polite_style(comment):
        return fallback
    return f"{fallback}\n{comment}"


async def synthesize_summary_comment(request: str, compact_payload: dict[str, Any]) -> str:
    from agent.auxiliary_client import async_call_llm

    response = await async_call_llm(
        task=ROUTER_TASK,
        provider=COMMENTARY_PROVIDER,
        model=COMMENTARY_MODEL,
        messages=summary_comment_messages(request, compact_payload),
        temperature=0.2,
        max_tokens=80,
        timeout=SUMMARY_COMMENT_TIMEOUT_SECONDS,
        extra_body=COMMENTARY_EXTRA_BODY,
    )
    return _response_content(response).strip()


def summary_comment_messages(request: str, compact_payload: dict[str, Any]) -> list[dict[str, str]]:
    facts = json.dumps(compact_payload, ensure_ascii=False)
    return [
        {
            "role": "system",
            "content": (
                "너는 미호야. 조회 결과 아래에 붙일 짧은 한 줄 코멘트만 써. "
                "현재 사용자에게 말하듯 자연스러운 한국어 반말로 답해. "
                "존대, 보고서 말투, 상담원 말투는 쓰지 마. "
                "JSON에 없는 사실은 만들지 마. "
                "숫자, 날짜, 학생명, 결석, 지각, 미체크 값은 절대 바꾸지 마. "
                "upcoming 또는 예정 상태는 아직 오지 않은 수업이라 미체크나 문제로 보지 마. "
                "새 목록을 만들지 말고 운영상 확인 포인트만 한 문장으로 말해."
            ),
        },
        {"role": "user", "content": f"요청: {request}\n조회 JSON: {facts}"},
    ]


def _response_content(response: Any) -> str:
    try:
        return str(response.choices[0].message.content or "")
    except (AttributeError, IndexError, TypeError):
        return str(response or "")


def _has_polite_style(text: str) -> bool:
    compact = text.replace(" ", "")
    return any(suffix in compact for suffix in POLITE_SUFFIXES)
