"""LLM-based final QA agent contract for Governance OS."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from plugins.governance_os import final_qa


def test_verdict_fail_closed_for_governed_answer_when_reviewer_unavailable(monkeypatch) -> None:
    async def boom(*_a: object, **_k: object) -> str:
        raise RuntimeError("reviewer offline")

    monkeypatch.setattr(final_qa, "_request_verdict", boom)

    verdict = asyncio.run(
        final_qa.verdict_or_pass(
            "서연이 수시 환산점수 계산해줘",
            "서연이 수시 환산점수는 947.3점입니다.",
            evidence={"playbook_key": "susi_score_calculation"},
        )
    )

    assert verdict == final_qa.REVISE_VERDICT


def test_verdict_fail_open_for_general_answer_when_reviewer_unavailable(monkeypatch) -> None:
    async def boom(*_a: object, **_k: object) -> str:
        raise RuntimeError("reviewer offline")

    monkeypatch.setattr(final_qa, "_request_verdict", boom)

    verdict = asyncio.run(
        final_qa.verdict_or_pass(
            "파이썬 GIL이 뭐야?",
            "GIL은 한 번에 하나의 스레드만 바이트코드를 실행하게 합니다.",
            evidence={},
        )
    )

    assert verdict == final_qa.PASS_VERDICT


class _Msg:
    def __init__(self, content: str) -> None:
        self.message = type("M", (), {"content": content})()


class _Resp:
    def __init__(self, content: str) -> None:
        self.choices = [_Msg(content)]


_FAILURE_SIGNAL_LITERALS = ("못 찾", "없어", "기록 없음", "0명", "찾을 수 없")


def test_final_qa_runtime_has_no_failure_signal_keyword_matching() -> None:
    src = Path("plugins/governance_os/final_qa.py").read_text(encoding="utf-8")
    offenders = [
        lit
        for lit in _FAILURE_SIGNAL_LITERALS
        if re.search(rf'["\'][^"\']*{re.escape(lit)}[^"\']*["\']\s*(in|==)\s+\w', src)
        or re.search(rf'\w+\s*(in|==)\s*["\'][^"\']*{re.escape(lit)}', src)
    ]
    assert offenders == [], f"final QA must be LLM-judged, not keyword-matched: {offenders}"


def test_final_qa_messages_carry_question_answer_and_evidence() -> None:
    messages = final_qa.verdict_messages(
        "미호 가버넌스 점수 매겨줘",
        "수시 점수 계산 도구를 다시 실행해 주세요.",
        evidence={"tools": ["none"], "reviewers": ["none"]},
    )

    assert messages[0]["role"] == "system"
    assert "pass" in messages[0]["content"]
    assert "revise" in messages[0]["content"]
    assert "미호 가버넌스 점수 매겨줘" in messages[1]["content"]
    assert "수시 점수 계산 도구를 다시 실행해 주세요." in messages[1]["content"]
    assert "reviewers" in messages[1]["content"]


def test_final_qa_repair_messages_carry_rewrite_contract() -> None:
    messages = final_qa.repair_messages(
        "미호 거버넌스 점수 매겨줘",
        "전용 도구를 다시 실행해 주세요.",
        evidence={"review": "missing"},
    )

    assert messages[0]["role"] == "system"
    assert "새 최종 답변" in messages[0]["content"]
    assert "내부" in messages[0]["content"]
    assert "미호 거버넌스 점수 매겨줘" in messages[1]["content"]
    assert "review" in messages[1]["content"]


@pytest.mark.asyncio
async def test_final_qa_verdict_revise_when_llm_says_revise(monkeypatch) -> None:
    async def fake_call(*args, **kwargs):
        return _Resp("revise")

    monkeypatch.setattr("agent.auxiliary_client.async_call_llm", fake_call)

    assert await final_qa.verdict_or_pass("Q", "A") == final_qa.REVISE_VERDICT


@pytest.mark.asyncio
async def test_final_qa_verdict_pass_when_llm_says_pass(monkeypatch) -> None:
    async def fake_call(*args, **kwargs):
        return _Resp("pass")

    monkeypatch.setattr("agent.auxiliary_client.async_call_llm", fake_call)

    assert await final_qa.verdict_or_pass("Q", "A") == final_qa.PASS_VERDICT


@pytest.mark.asyncio
async def test_final_qa_transport_failure_is_not_user_visible(monkeypatch) -> None:
    async def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("agent.auxiliary_client.async_call_llm", boom)

    assert await final_qa.verdict_or_pass("Q", "A") == final_qa.PASS_VERDICT


def test_final_qa_repair_uses_llm_rewrite(monkeypatch) -> None:
    def fake_call(*args, **kwargs):
        return _Resp("사용자 질문에 맞춘 새 답변입니다.")

    monkeypatch.setattr("agent.auxiliary_client.call_llm", fake_call)

    repaired = final_qa.repair_answer_or_original(
        "점수를 매겨줘",
        "전용 도구를 다시 실행해 주세요.",
        evidence={"verdict": "revise"},
    )

    assert repaired == "사용자 질문에 맞춘 새 답변입니다."


def test_final_qa_repair_failure_keeps_nonempty_answer(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("agent.auxiliary_client.call_llm", boom)

    assert final_qa.repair_answer_or_original("Q", "A") == "A"


def test_final_qa_repair_loop_verifies_repaired_answer_with_llm(monkeypatch) -> None:
    calls: list[str] = []

    def fake_call(*args, **kwargs):
        task = str(kwargs.get("task") or "")
        calls.append(task)
        if task == final_qa.FINAL_QA_REPAIR_TASK:
            return _Resp("사용자 질문에 맞춘 새 답변입니다.")
        return _Resp("pass")

    monkeypatch.setattr("agent.auxiliary_client.call_llm", fake_call)

    repaired = final_qa.repair_answer_until_pass(
        "점수를 매겨줘",
        "전용 도구를 다시 실행해 주세요.",
        evidence={"verdict": "revise"},
    )

    assert repaired == "사용자 질문에 맞춘 새 답변입니다."
    assert calls == [final_qa.FINAL_QA_REPAIR_TASK, final_qa.FINAL_QA_TASK]


def test_final_qa_repair_loop_retries_when_final_qa_says_revise(monkeypatch) -> None:
    repair_count = 0
    verdict_count = 0

    def fake_call(*args, **kwargs):
        nonlocal repair_count, verdict_count
        task = str(kwargs.get("task") or "")
        if task == final_qa.FINAL_QA_REPAIR_TASK:
            repair_count += 1
            return _Resp(f"수정 답변 {repair_count}")
        verdict_count += 1
        return _Resp("revise" if verdict_count == 1 else "pass")

    monkeypatch.setattr("agent.auxiliary_client.call_llm", fake_call)

    repaired = final_qa.repair_answer_until_pass("Q", "A", max_attempts=2)

    assert repaired == "수정 답변 2"
    assert repair_count == 2
    assert verdict_count == 2


def test_final_qa_repair_loop_fallback_hides_internal_terms(monkeypatch) -> None:
    def boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr("agent.auxiliary_client.call_llm", boom)

    repaired = final_qa.repair_answer_until_pass(
        "Q",
        "이 결과는 전용 도구와 후검증 통과 기록이 없어 최종 전달할 수 없습니다.",
        max_attempts=1,
    )

    assert "전용 도구" not in repaired
    assert "후검증" not in repaired
    assert "provider" not in repaired
    assert "확인 근거" in repaired
