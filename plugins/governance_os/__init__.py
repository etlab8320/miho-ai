"""Miho Governance Agent OS plugin foundation."""

from __future__ import annotations

from typing import Any

from .dispatcher import governance_pre_gateway_dispatch
from .delivery_gate import governance_transform_llm_output
from .guard import governance_pre_tool_call
from .result_transform import governance_transform_tool_result


DISPATCHER_TASK = "miho_governance_dispatcher"
REVIEWER_TASK = "miho_governance_reviewer"
PROMOTION_JUDGE_TASK = "miho_governance_promotion_judge"

DISPATCHER_INSTRUCTIONS = (
    "요청을 Governance OS playbook으로 라우팅한다. "
    "required_tools, forbidden_tools, missing_context, review_gates를 먼저 확인하고 "
    "전용 도구 없이 최종 산출물을 만들지 못하게 재작성한다."
)
REVIEWER_INSTRUCTIONS = (
    "도구 결과를 사용자에게 전달하기 전 후검증한다. "
    "레이아웃, 산식, 근거, media_tag, artifact_path, 의도 일치를 확인하고 "
    "실패 시 사용자에게 완성본처럼 말하지 말고 retry_tools 재실행을 요구한다."
)
PROMOTION_JUDGE_INSTRUCTIONS = (
    "Outcome ledger의 반복 실패만 promotion 후보로 평가한다. "
    "evidence, tests_required, 구조화된 test_receipts, rollback 경로가 없으면 승격하지 않는다."
)


def register(ctx: Any) -> None:
    ctx.register_hook("pre_gateway_dispatch", governance_pre_gateway_dispatch)
    ctx.register_hook("pre_tool_call", governance_pre_tool_call)
    ctx.register_hook("transform_tool_result", governance_transform_tool_result)
    ctx.register_hook("transform_llm_output", governance_transform_llm_output)
    ctx.register_auxiliary_task(
        key=DISPATCHER_TASK,
        display_name="Miho governance dispatcher",
        description="Selects playbooks and agent chains for governed Miho requests",
        defaults={
            "provider": "auto",
            "timeout": 30,
            "extra_body": {"reasoning": {"effort": "low"}},
            "instructions": DISPATCHER_INSTRUCTIONS,
        },
    )
    ctx.register_auxiliary_task(
        key=REVIEWER_TASK,
        display_name="Miho governance reviewer",
        description="Reviews governed outputs before user-facing delivery",
        defaults={
            "provider": "auto",
            "timeout": 90,
            "extra_body": {"reasoning": {"effort": "medium"}},
            "instructions": REVIEWER_INSTRUCTIONS,
        },
    )
    ctx.register_auxiliary_task(
        key=PROMOTION_JUDGE_TASK,
        display_name="Miho governance promotion judge",
        description="Evaluates repeated failures before rule or playbook promotion",
        defaults={
            "provider": "auto",
            "timeout": 60,
            "extra_body": {"reasoning": {"effort": "medium"}},
            "instructions": PROMOTION_JUDGE_INSTRUCTIONS,
        },
    )


__all__ = [
    "DISPATCHER_TASK",
    "PROMOTION_JUDGE_TASK",
    "governance_transform_llm_output",
    "REVIEWER_TASK",
    "register",
]
