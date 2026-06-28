"""Goal-first Governance OS prompt contracts."""

from __future__ import annotations

from plugins.governance_os.final_delivery_agent import final_delivery_messages
from plugins.governance_os.final_delivery_orchestrator import (
    final_delivery_orchestrator_messages,
)


def test_final_delivery_agent_prompt_prefers_goal_completion_over_refusal() -> None:
    messages = final_delivery_messages(
        "맥미니 새 IP 직접 확인해줘",
        "확인할 수 없습니다.",
        evidence={"tool_results": []},
    )
    system = messages[0]["content"]

    assert "사용자 목표 달성" in system
    assert "불필요한 거절" in system


def test_final_delivery_orchestrator_prompt_uses_tools_before_needs_input() -> None:
    messages = final_delivery_orchestrator_messages(
        mode="plan_tools",
        question="크론이 실제로 돌았는지 확인해줘",
        answer="현재 확인할 수 없습니다.",
        playbook_key="dev_code_update",
        allowed_tools=("terminal",),
        conversation_history=[],
        evidence={},
    )
    system = messages[0]["content"]

    assert "안전한 도구로 먼저 확인" in system
    assert "보모식 거절" in system
    assert "필수 입력" in system
