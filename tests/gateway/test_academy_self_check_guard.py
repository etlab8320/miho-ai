"""Gateway self-check guard for academy follow-up answers.

The guard runs only on an academy follow-up turn (event.academy_self_check set
by the academy hook). It asks an LLM whether the body's answer fits the
question; on verdict=retry it re-runs the body ONCE with a strengthened
channel_prompt. Plain (non-academy) turns never set the signal, so the gateway
never enters the guard for them — speed is preserved.

These tests drive _academy_self_check_retry directly on a minimal fake self
(the full GatewayRunner is too heavy to construct), stubbing _run_agent and
_reply_anchor_for_event. The verdict LLM is monkeypatched on the self_check
module so no network call is made.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import gateway.run as gateway_run
from plugins.academy_ops import self_check
from gateway.config import Platform


class _FakeSelf:
    """Minimal stand-in exposing only what the guard touches."""

    def __init__(self, retry_result):
        self._retry_result = retry_result
        self.run_agent_calls = []

    def _reply_anchor_for_event(self, event):
        return None

    async def _run_agent(self, **kwargs):
        self.run_agent_calls.append(kwargs)
        return self._retry_result


def _source():
    return SimpleNamespace(platform=Platform.DISCORD)


async def _invoke(fake_self, event, answer="오늘 출석한 학생은 0명이야."):
    return await gateway_run.GatewayRunner._academy_self_check_retry(
        fake_self,
        question="오늘 출석 예정 학생 알려줘",
        answer=answer,
        context_prompt="ctx",
        history=[],
        source=_source(),
        session_entry=SimpleNamespace(session_id="sid"),
        session_key="sk",
        run_generation=1,
        event=event,
    )


@pytest.mark.asyncio
async def test_retry_reruns_body_with_strengthened_prompt(monkeypatch) -> None:
    async def verdict(*a, **k):
        return self_check.RETRY_VERDICT

    monkeypatch.setattr(self_check, "verdict_or_ok", verdict)
    fake = _FakeSelf({"final_response": "출석 예정 학생은 12명이야."})
    event = SimpleNamespace(channel_prompt="직전 맥락", academy_self_check=True)

    result = await _invoke(fake, event)

    assert result is not None
    agent_result, response = result
    assert response == "출석 예정 학생은 12명이야."
    # Body was re-run exactly once with a strengthened channel_prompt that keeps
    # the prior context and adds the correction instruction.
    assert len(fake.run_agent_calls) == 1
    sent_prompt = fake.run_agent_calls[0]["channel_prompt"]
    assert "직전 맥락" in sent_prompt
    assert "맞지 않" in sent_prompt  # correction instruction present


@pytest.mark.asyncio
async def test_ok_verdict_keeps_original_answer_no_rerun(monkeypatch) -> None:
    async def verdict(*a, **k):
        return self_check.OK_VERDICT

    monkeypatch.setattr(self_check, "verdict_or_ok", verdict)
    fake = _FakeSelf({"final_response": "should-not-be-used"})
    event = SimpleNamespace(channel_prompt="x", academy_self_check=True)

    result = await _invoke(fake, event)

    assert result is None  # keep original answer
    assert fake.run_agent_calls == []  # body never re-run


def test_guard_is_gated_by_academy_self_check_signal_only() -> None:
    """The gateway enters the self-check guard solely via the state flag the
    academy hook sets — never via keywords. A non-academy turn has no
    academy_self_check attribute, so getattr(..., False) skips the guard and
    its verdict LLM is never called (speed preserved). This pins that gate so a
    future edit can't widen it into keyword/text matching."""
    from pathlib import Path

    src = Path("gateway/run.py").read_text(encoding="utf-8").splitlines()
    guard_line = next(
        line for line in src
        if "_academy_self_check_retry(" in line and "def " not in line
    )
    # Walk back to the enclosing `if` that guards the call.
    idx = src.index(next(l for l in src if "retried = await self._academy_self_check_retry" in l))
    gate = next(src[i] for i in range(idx, idx - 6, -1) if src[i].strip().startswith("if "))
    assert 'getattr(event, "academy_self_check", False)' in gate
    # A bare non-academy event genuinely lacks the attribute -> guard skipped.
    plain_event = SimpleNamespace()
    assert getattr(plain_event, "academy_self_check", False) is False


@pytest.mark.asyncio
async def test_retry_with_empty_rerun_keeps_original(monkeypatch) -> None:
    async def verdict(*a, **k):
        return self_check.RETRY_VERDICT

    monkeypatch.setattr(self_check, "verdict_or_ok", verdict)
    # Retry produced the "(empty)" sentinel -> not better, keep the original.
    fake = _FakeSelf({"final_response": "(empty)"})
    event = SimpleNamespace(channel_prompt=None, academy_self_check=True)

    result = await _invoke(fake, event)
    assert result is None
    assert len(fake.run_agent_calls) == 1  # tried once, then gave up
