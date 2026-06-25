"""Miho Governance Agent OS plugin foundation."""

from __future__ import annotations

from typing import Any

from .dispatcher import governance_pre_gateway_dispatch
from .delivery_gate import governance_transform_llm_output
from .final_qa import FINAL_QA_REPAIR_TASK, FINAL_QA_TASK
from .guard import governance_pre_tool_call
from .result_transform import governance_transform_tool_result


DISPATCHER_TASK = "miho_governance_dispatcher"
REVIEWER_TASK = "miho_governance_reviewer"
PROMOTION_JUDGE_TASK = "miho_governance_promotion_judge"
SELF_HARNESS_WEAKNESS_MINER_TASK = "miho_self_harness_weakness_miner"
SELF_HARNESS_PROPOSER_TASK = "miho_self_harness_proposer"

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
SELF_HARNESS_WEAKNESS_MINER_INSTRUCTIONS = (
    "Self-Harness Weakness Mining 단계다. Outcome ledger와 reviewer evidence에서 반복 실패를 묶되 "
    "active registry, runtime policy, 기존 playbook은 절대 수정하지 않는다. "
    "패턴은 playbook_key, failure_signature, recurrence_count, evidence, target_surface_hint로만 보고한다."
)
SELF_HARNESS_PROPOSER_INSTRUCTIONS = (
    "Self-Harness shadow proposer다. 반복 실패 패턴을 최소 변경 후보로 바꾸되 "
    "status=shadow_candidate, auto_promote_allowed=false, held-in/held-out validation, rollback을 반드시 포함한다. "
    "기존 미호 동작은 새 후보 검증이 끝날 때까지 바꾸지 않는다. "
    "검증 receipt가 모두 통과하면 사용자 승인 없이 activation으로 넘기고, regression 실패 시 rollback을 요구한다."
)
FINAL_QA_INSTRUCTIONS = (
    "사용자 질문과 최종 답변 후보를 대조하는 LLM 기반 마지막 안전장치다. "
    "도메인 도구 검수는 각 reviewer가 맡고, Final QA는 답변이 질문에 맞는지, "
    "내부 guard/retry 문구가 노출되지 않는지, evidence와 모순되지 않는지만 판단한다. "
    "수정 필요 시 revise, 전달 가능하면 pass만 반환한다."
)
FINAL_QA_REPAIR_INSTRUCTIONS = (
    "Final QA가 revise하거나 delivery gate가 내부 검증 문구를 노출할 위험이 있을 때 "
    "사용자에게 보낼 새 최종 답변만 작성하는 LLM repair agent다. "
    "repair 뒤에는 Final QA agent가 다시 pass/revise를 판정하는 루프로 검수한다. "
    "내부 guard, retry_tools, stack trace, provider 오류를 숨기고 한국어 평문으로 질문에 직접 답한다."
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
    ctx.register_auxiliary_task(
        key=SELF_HARNESS_WEAKNESS_MINER_TASK,
        display_name="Miho Self-Harness weakness miner",
        description="Mines repeated governance failures without changing active behavior",
        defaults={
            "provider": "auto",
            "timeout": 60,
            "extra_body": {"reasoning": {"effort": "medium"}},
            "instructions": SELF_HARNESS_WEAKNESS_MINER_INSTRUCTIONS,
        },
    )
    ctx.register_auxiliary_task(
        key=SELF_HARNESS_PROPOSER_TASK,
        display_name="Miho Self-Harness shadow proposer",
        description="Proposes shadow-only harness candidates with validation and rollback gates",
        defaults={
            "provider": "auto",
            "timeout": 60,
            "extra_body": {"reasoning": {"effort": "medium"}},
            "instructions": SELF_HARNESS_PROPOSER_INSTRUCTIONS,
        },
    )
    ctx.register_auxiliary_task(
        key=FINAL_QA_TASK,
        display_name="Miho governance final QA agent",
        description="Checks whether the final answer fits the user request before delivery",
        defaults={
            "provider": "auto",
            "timeout": 30,
            "extra_body": {"reasoning": {"effort": "low"}},
            "instructions": FINAL_QA_INSTRUCTIONS,
        },
    )
    ctx.register_auxiliary_task(
        key=FINAL_QA_REPAIR_TASK,
        display_name="Miho governance final QA repair agent",
        description="Rewrites blocked or mismatched governed answers before delivery",
        defaults={
            "provider": "auto",
            "timeout": 20,
            "extra_body": {"reasoning": {"effort": "medium"}},
            "instructions": FINAL_QA_REPAIR_INSTRUCTIONS,
        },
    )


__all__ = [
    "DISPATCHER_TASK",
    "FINAL_QA_REPAIR_TASK",
    "FINAL_QA_TASK",
    "PROMOTION_JUDGE_TASK",
    "SELF_HARNESS_PROPOSER_TASK",
    "SELF_HARNESS_WEAKNESS_MINER_TASK",
    "governance_transform_llm_output",
    "REVIEWER_TASK",
    "register",
]
