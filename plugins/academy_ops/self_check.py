"""LLM self-check verdict for academy follow-up answers.

An academy follow-up turn (ALLOW with prior thread context) can still produce a
wrong answer: the body agent picks the wrong tool (e.g. a past-record lookup for
a question about an *upcoming* schedule) and replies "0명" / "기록 없음". The
prompt-level self-check (format_context_note) nudges the body to self-correct,
but as a safety net the gateway runs this one-shot verdict on the final answer.

The verdict is produced ENTIRELY by the LLM — there is no Korean failure-signal
keyword matching here (owner's permanent rule). The model is told what an
inadequate answer looks like (empty / "couldn't find" / off-topic) and returns a
single token verdict. On any error or timeout the caller keeps the original
answer (safety first — the guard must never block a reply).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .commentary_config import (
    COMMENTARY_EXTRA_BODY,
    COMMENTARY_MODEL,
    COMMENTARY_PROVIDER,
)


logger = logging.getLogger(__name__)
SELF_CHECK_TASK = "academy_request_router"
SELF_CHECK_TIMEOUT_SECONDS = 5
RETRY_VERDICT = "retry"
OK_VERDICT = "ok"


async def verdict_or_ok(question: str, answer: str) -> str:
    """Return "retry" if the LLM judges the answer inadequate, else "ok".

    Any failure (timeout, provider error, empty/garbled verdict) returns "ok"
    so the original answer is kept — the guard never blocks a reply.
    """
    if not str(question or "").strip() or not str(answer or "").strip():
        return OK_VERDICT
    try:
        raw = await asyncio.wait_for(
            _request_verdict(question, answer),
            SELF_CHECK_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.info("academy self-check skipped: %s", exc)
        return OK_VERDICT
    return RETRY_VERDICT if _is_retry(raw) else OK_VERDICT


async def _request_verdict(question: str, answer: str) -> str:
    from agent.auxiliary_client import async_call_llm

    response = await async_call_llm(
        task=SELF_CHECK_TASK,
        provider=COMMENTARY_PROVIDER,
        model=COMMENTARY_MODEL,
        messages=verdict_messages(question, answer),
        temperature=0.0,
        max_tokens=8,
        timeout=SELF_CHECK_TIMEOUT_SECONDS,
        extra_body=COMMENTARY_EXTRA_BODY,
    )
    return _response_content(response).strip()


def verdict_messages(question: str, answer: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "너는 미호의 답변 검수자야. 사용자 질문 Q와 미호가 낸 답 A를 받는다. "
                "A가 Q에 대한 적절한 답인지 판정해. "
                "답이 비어 있거나, 원하는 정보를 못 찾았다는 식의 실패이거나, "
                "질문과 동떨어진 엉뚱한 내용이면 부적절하다고 본다. "
                "부적절하면 정확히 'retry' 한 단어만, 적절하면 정확히 'ok' 한 단어만 출력해. "
                "다른 말은 절대 붙이지 마."
            ),
        },
        {"role": "user", "content": f"Q: {question}\nA: {answer}"},
    ]


def _is_retry(verdict: str) -> bool:
    return RETRY_VERDICT in verdict.strip().lower()


def _response_content(response: Any) -> str:
    try:
        return str(response.choices[0].message.content or "")
    except (AttributeError, IndexError, TypeError):
        return str(response or "")
