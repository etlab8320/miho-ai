"""Self-check verdict guard for academy follow-up answers.

The body agent can still misroute an academy follow-up (e.g. a past-record tool
for an *upcoming* schedule question) and reply "0명". As a safety net, the
gateway asks an LLM whether the answer fits the question before sending it.

Guards under test:
1. The verdict is produced by the LLM — there is NO Korean failure-signal
   keyword matching in the runtime (owner's permanent rule). Static check.
2. verdict_or_ok routes the LLM's answer to retry/ok and is fail-safe (any
   error/timeout -> ok, so the guard never blocks a reply).
3. The academy hook sets event.academy_self_check ONLY on an ALLOW follow-up
   that carries prior context; plain turns leave it unset (the gateway then
   skips the guard, preserving speed).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from plugins.academy_ops import self_check
from plugins.academy_ops import thread_context as tc


@pytest.fixture(autouse=True)
def _clear():
    tc.clear_thread_contexts()
    yield
    tc.clear_thread_contexts()


class _Msg:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _Resp:
    def __init__(self, content):
        self.choices = [_Msg(content)]


# --- 1. No hardcoded failure-signal keywords (LLM judges, not the code) ---

# Korean failure-signal phrases the owner's rule forbids baking into the guard
# as control-flow literals. The verdict must come from the LLM, so these must
# not appear as decision keywords matched against the answer text.
_FAILURE_SIGNAL_LITERALS = ("못 찾", "없어", "기록 없음", "0명", "찾을 수 없")


def test_self_check_runtime_has_no_failure_signal_keyword_matching() -> None:
    src = Path("plugins/academy_ops/self_check.py").read_text(encoding="utf-8")
    # Strip the docstring/prompt strings: the only Korean allowed is inside the
    # LLM prompt (system/user content), never as a Python `in`/`==` comparison
    # against the answer. The check below targets comparison usage specifically.
    offenders = [
        lit for lit in _FAILURE_SIGNAL_LITERALS
        if re.search(rf'["\'][^"\']*{re.escape(lit)}[^"\']*["\']\s*(in|==)\s+\w', src)
        or re.search(rf'\w+\s*(in|==)\s*["\'][^"\']*{re.escape(lit)}', src)
    ]
    assert offenders == [], f"failure-signal keyword matching is forbidden: {offenders}"


def test_verdict_messages_carry_question_and_answer_to_llm() -> None:
    msgs = self_check.verdict_messages("출석 예정 학생?", "오늘 출석한 학생은 0명이야.")
    assert msgs[0]["role"] == "system"
    assert "retry" in msgs[0]["content"] and "ok" in msgs[0]["content"]
    assert "출석 예정 학생?" in msgs[1]["content"]
    assert "0명" in msgs[1]["content"]


# --- 2. verdict routing + fail-safe ---

@pytest.mark.asyncio
async def test_verdict_retry_when_llm_says_retry(monkeypatch) -> None:
    async def fake(*a, **k):
        return _Resp("retry")

    monkeypatch.setattr("agent.auxiliary_client.async_call_llm", fake)
    assert await self_check.verdict_or_ok("Q", "A") == self_check.RETRY_VERDICT


@pytest.mark.asyncio
async def test_verdict_ok_when_llm_says_ok(monkeypatch) -> None:
    async def fake(*a, **k):
        return _Resp("ok")

    monkeypatch.setattr("agent.auxiliary_client.async_call_llm", fake)
    assert await self_check.verdict_or_ok("Q", "A") == self_check.OK_VERDICT


@pytest.mark.asyncio
async def test_verdict_failsafe_keeps_ok_on_llm_error(monkeypatch) -> None:
    async def boom(*a, **k):
        raise RuntimeError("provider down")

    monkeypatch.setattr("agent.auxiliary_client.async_call_llm", boom)
    # An LLM failure must never block the reply -> treated as ok.
    assert await self_check.verdict_or_ok("Q", "A") == self_check.OK_VERDICT


@pytest.mark.asyncio
async def test_verdict_ok_for_blank_inputs() -> None:
    assert await self_check.verdict_or_ok("", "A") == self_check.OK_VERDICT
    assert await self_check.verdict_or_ok("Q", "") == self_check.OK_VERDICT


# --- 3. State-based signal: set only on academy follow-up with prior context ---

class _Src:
    platform = type("P", (), {"value": "discord"})()
    guild_id = "g"
    chat_id = "c"
    thread_id = "t"
    user_id = "u"


class _Event:
    def __init__(self):
        self.source = _Src()
        self.channel_prompt = None


def test_inject_prior_context_returns_true_when_context_exists() -> None:
    from plugins.academy_ops import _inject_prior_context

    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_monthly_test_records",
        args={},
        payload={"ok": True, "test": {"id": 13, "test_month": "2026-05"}},
    )
    ev = _Event()
    assert _inject_prior_context(ev, key) is True
    assert ev.channel_prompt


def test_inject_prior_context_returns_false_without_context() -> None:
    from plugins.academy_ops import _inject_prior_context

    ev = _Event()
    assert _inject_prior_context(ev, "missing") is False
    assert ev.channel_prompt is None
