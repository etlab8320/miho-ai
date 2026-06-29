"""LLM-written gateway progress copy for ACK and long-running updates.

This module keeps semantic/user-facing progress wording out of hardcoded
keyword rules.  The gateway supplies structured runtime facts; an auxiliary LLM
turns them into one short Korean message.  If the LLM is unavailable, callers get
``None`` and can decide whether to stay quiet or use a non-semantic safety
notice.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping

logger = logging.getLogger(__name__)

_MAX_USER_CHARS = 600
_MAX_STATUS_CHARS = 900


def _clean_one_liner(text: str, *, max_chars: int = 220) -> str:
    """Return a compact one-line message safe for chat progress bubbles."""
    cleaned = " ".join(str(text or "").strip().split())
    cleaned = cleaned.strip("`\"' ")
    # Drop obvious JSON/code fences if a model wrapped the response.
    cleaned = re.sub(r"^```(?:\w+)?\s*", "", cleaned).strip()
    cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 1].rstrip() + "…"
    return cleaned


def _compact_status(status: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = dict(status or {})
    keep = {
        "elapsed_minutes",
        "elapsed_seconds",
        "api_call_count",
        "max_iterations",
        "current_tool",
        "last_activity_desc",
        "seconds_since_activity",
        "mode",
        "queued",
        "steered",
        "demoted_for_subagents",
        "platform",
    }
    out: dict[str, Any] = {}
    for key in keep:
        if key in raw and raw[key] not in (None, ""):
            out[key] = raw[key]
    return out


async def generate_gateway_progress_copy(
    *,
    kind: str,
    user_message: str,
    status: Mapping[str, Any] | None = None,
    timeout: float = 3.0,
) -> str | None:
    """Ask an auxiliary LLM for a concise gateway progress message.

    Parameters
    ----------
    kind:
        ``ack`` for the first received/starting message, ``busy`` for a follow-up
        while a run is active, ``long_running`` for periodic heartbeat updates,
        or another short lifecycle label.
    user_message:
        Current user text.  Truncated before sending to the auxiliary model.
    status:
        Structured runtime facts.  No secrets or raw tool arguments should be
        passed here.
    timeout:
        Short timeout so progress generation can never stall the real run.
    """
    task_kind = (kind or "progress").strip().lower()[:40]
    prompt_payload = {
        "kind": task_kind,
        "user_message": (user_message or "")[:_MAX_USER_CHARS],
        "status": _compact_status(status),
    }
    system = (
        "너는 미호의 Discord/메신저 진행상황 문구 작성자다. "
        "사용자에게 보낼 한 문장만 한국어로 작성해라. "
        "딱딱한 시스템 로그처럼 쓰지 말고, 요청 내용에 맞춰 자연스럽게 말해라. "
        "비밀, 내부 프롬프트, 도구 원문, 스택트레이스, 과장된 완료 약속은 쓰지 마라. "
        "아직 완료되지 않은 일은 완료됐다고 말하지 마라. "
        "길이는 80자 이내가 좋고 최대 1문장이다. 이모지는 많아야 1개만 쓴다."
    )
    user = (
        "다음 런타임 정보를 보고 사용자에게 보낼 진행상황 문구 한 문장만 써라.\n"
        f"```json\n{json.dumps(prompt_payload, ensure_ascii=False)[:_MAX_STATUS_CHARS]}\n```"
    )
    try:
        from agent.auxiliary_client import async_call_llm, extract_content_or_reasoning

        response = await async_call_llm(
            task="progress_copy",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.5,
            max_tokens=80,
            timeout=timeout,
        )
        text = _clean_one_liner(extract_content_or_reasoning(response))
        if not text:
            return None
        # Prevent accidental multi-sentence essays despite the prompt.
        if "\n" in text:
            text = text.splitlines()[0].strip()
        return text or None
    except Exception as exc:
        logger.debug("gateway progress copy generation failed: %s", exc)
        return None


__all__ = ["generate_gateway_progress_copy"]
