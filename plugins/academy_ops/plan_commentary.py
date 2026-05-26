"""LLM-only commentary for Peak daily plan facts."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from .commentary_config import (
    COMMENTARY_ERROR_MESSAGE,
    COMMENTARY_EXTRA_BODY,
    COMMENTARY_FALLBACK_MODELS,
    COMMENTARY_FALLBACK_TIMEOUT_SECONDS,
    COMMENTARY_MODEL,
    COMMENTARY_OUTER_TIMEOUT_SECONDS,
    COMMENTARY_PROVIDER,
    COMMENTARY_TASK,
    COMMENTARY_TIMEOUT_MESSAGE,
    COMMENTARY_TIMEOUT_SECONDS,
)


logger = logging.getLogger(__name__)
CommentaryCaller = Callable[[dict[str, Any]], Awaitable[str]]


def plan_commentary_facts(payload: dict[str, Any]) -> dict[str, Any]:
    plans = [plan for plan in payload.get("plans", []) if isinstance(plan, dict)]
    if not plans:
        return {}
    plan = plans[0]
    exercises = [
        {
            "name": str(item.get("name") or ""),
            "note": str(item.get("note") or ""),
            "completed": bool(item.get("completed")),
        }
        for item in plan.get("exercises", [])
        if isinstance(item, dict)
    ]
    return {
        "date": str(payload.get("date") or plan.get("date") or ""),
        "instructor_name": str(plan.get("instructor_name") or ""),
        "time_slot": str(plan.get("time_slot") or ""),
        "completed_count": int(plan.get("completed_count") or 0),
        "exercise_count": len(exercises),
        "exercises": exercises,
    }


def plan_commentary_messages(facts: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "너는 미호야. 제공된 JSON 사실만 보고 한국어 코멘트 1~2문장을 써. "
                "운동명과 메모에서 어떤 운동 위주였는지 자연스럽게 요약하되, "
                "없는 분류명이나 없는 사실을 만들지 마. 보고서 말투 말고 짧게 말해."
            ),
        },
        {
            "role": "user",
            "content": f"운동계획 JSON:\n{facts}",
        },
    ]


async def generate_plan_commentary(payload: dict[str, Any]) -> str:
    facts = plan_commentary_facts(payload)
    if not facts:
        return ""
    from agent.auxiliary_client import async_call_llm

    messages = plan_commentary_messages(facts)
    try:
        response = await _call_plan_commentary_llm(
            async_call_llm,
            messages=messages,
            model=COMMENTARY_MODEL,
            timeout=COMMENTARY_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        response = await _fallback_plan_commentary(async_call_llm, messages)
    content = response.choices[0].message.content
    return str(content or "").strip()


async def _fallback_plan_commentary(
    async_call_llm: Any,
    messages: list[dict[str, str]],
) -> Any:
    last_error: TimeoutError | None = None
    for model in COMMENTARY_FALLBACK_MODELS:
        try:
            return await _call_plan_commentary_llm(
                async_call_llm,
                messages=messages,
                model=model,
                timeout=COMMENTARY_FALLBACK_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            last_error = exc
            logger.info("academy plan commentary fallback timed out: %s", model)
    if last_error is not None:
        raise last_error
    raise TimeoutError("academy plan commentary fallback timed out")


async def _call_plan_commentary_llm(
    async_call_llm: Any,
    *,
    messages: list[dict[str, str]],
    model: str,
    timeout: int,
) -> Any:
    return await async_call_llm(
        task=COMMENTARY_TASK,
        provider=COMMENTARY_PROVIDER,
        model=model,
        messages=messages,
        temperature=0.2,
        max_tokens=180,
        timeout=timeout,
        extra_body=COMMENTARY_EXTRA_BODY,
    )


def schedule_plan_commentary(
    *,
    gateway: Any,
    event: Any,
    payload: dict[str, Any],
    caller: CommentaryCaller = generate_plan_commentary,
) -> bool:
    if gateway is None or event is None:
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return False
    task = loop.create_task(_send_commentary(gateway, event, payload, caller))
    task.add_done_callback(_log_task_failure)
    return True


async def _send_commentary(
    gateway: Any,
    event: Any,
    payload: dict[str, Any],
    caller: CommentaryCaller,
) -> None:
    source = getattr(event, "source", None)
    adapter = getattr(gateway, "adapters", {}).get(getattr(source, "platform", None))
    if adapter is None or source is None:
        return
    try:
        commentary = await asyncio.wait_for(caller(payload), timeout=COMMENTARY_OUTER_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        logger.info(
            "academy plan commentary skipped: %s: %s",
            type(exc).__name__,
            exc,
        )
        await _send_commentary_notice(gateway, adapter, source, event, COMMENTARY_TIMEOUT_MESSAGE)
        return
    except Exception as exc:
        logger.info(
            "academy plan commentary skipped: %s: %s",
            type(exc).__name__,
            exc,
        )
        await _send_commentary_notice(gateway, adapter, source, event, COMMENTARY_ERROR_MESSAGE)
        return
    text = commentary.strip()
    if not text:
        return
    metadata = gateway._thread_metadata_for_source(source, gateway._reply_anchor_for_event(event))
    await adapter.send(source.chat_id, f"미호 코멘트: {text}", metadata=metadata)


async def _send_commentary_notice(
    gateway: Any,
    adapter: Any,
    source: Any,
    event: Any,
    message: str,
) -> None:
    metadata = gateway._thread_metadata_for_source(source, gateway._reply_anchor_for_event(event))
    await adapter.send(source.chat_id, message, metadata=metadata)


def _log_task_failure(task: asyncio.Task) -> None:
    try:
        task.result()
    except Exception:
        logger.warning("academy plan commentary task failed", exc_info=True)
