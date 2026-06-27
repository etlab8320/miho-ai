"""Regression tests for Governance OS final-hook fail-closed behavior."""

from __future__ import annotations

from plugins.governance_os import delivery_gate


def test_hook_exception_does_not_fail_open_for_governed_claim(monkeypatch) -> None:
    original = "서연이 수시 환산점수는 947.3점입니다."

    def broken_registry() -> object:
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(delivery_gate, "load_runtime_registry", broken_registry)

    transformed = delivery_gate.governance_transform_llm_output(
        response_text=original,
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
    )

    assert transformed
    assert transformed != original
    assert "947.3점" not in transformed
    assert "hook" not in transformed.casefold()
    assert "guard" not in transformed.casefold()
    assert "retry" not in transformed.casefold()


def test_hook_exception_keeps_plain_ungoverned_answer(monkeypatch) -> None:
    original = "오늘 회의 요약은 세 가지입니다."

    def broken_registry() -> object:
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(delivery_gate, "load_runtime_registry", broken_registry)

    transformed = delivery_gate.governance_transform_llm_output(
        response_text=original,
        user_message="회의 요약해줘",
        governance_outcomes=[],
    )

    assert transformed is None
