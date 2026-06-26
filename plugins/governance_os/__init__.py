"""Miho Governance Agent OS plugin foundation."""

from __future__ import annotations

from typing import Any

from .dispatcher import governance_pre_gateway_dispatch
from .delivery_gate import governance_transform_llm_output
from .final_delivery_agent import FINAL_DELIVERY_TASK
from .final_qa import FINAL_QA_REPAIR_TASK, FINAL_QA_TASK
from .guard import governance_pre_tool_call
from .result_transform import governance_transform_tool_result


DISPATCHER_TASK = "miho_governance_dispatcher"
REVIEWER_TASK = "miho_governance_reviewer"
ACADEMY_REVIEWER_TASK = "miho_governance_reviewer_academy"
DELIVERY_REVIEWER_TASK = "miho_governance_reviewer_delivery"
DEV_REVIEWER_TASK = "miho_governance_reviewer_dev"
RESEARCH_REVIEWER_TASK = "miho_governance_reviewer_research"
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
ACADEMY_REVIEWER_INSTRUCTIONS = REVIEWER_INSTRUCTIONS + (
    " 학원/입시 도메인 전담 reviewer로서 학생별 점수, 수시/학종/실기 추천, "
    "생기부 근거와 산식 일치를 의미 검수한다."
)
DELIVERY_REVIEWER_INSTRUCTIONS = REVIEWER_INSTRUCTIONS + (
    " 첨부/파일 전송 도메인 전담 reviewer로서 artifact_path, safe staging path, "
    "MEDIA tag, 실제 첨부 가능 위치를 의미 검수한다."
)
DEV_REVIEWER_INSTRUCTIONS = REVIEWER_INSTRUCTIONS + (
    " 개발/운영 도메인 전담 reviewer로서 테스트, diff scope, rollback, 배포 안전성을 의미 검수한다."
)
RESEARCH_REVIEWER_INSTRUCTIONS = REVIEWER_INSTRUCTIONS + (
    " 리서치 도메인 전담 reviewer로서 출처, 최신성, 인용 가능성, 과장 표현을 의미 검수한다."
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
FINAL_DELIVERY_INSTRUCTIONS = (
    "Final Delivery Agent로서 사용자 질문과 최종 답변 후보, 도구/reviewer evidence를 보고 "
    "실제 사용자에게 보낼 최종 본문을 결정한다. "
    "Python guard가 사용자 문구를 생성하지 않도록 deliver/revise/block JSON을 반환한다. "
    "거버넌스/셀프하네스 적대적 리뷰 요청은 도메인 단어가 있어도 리뷰 결과로 취급하고, "
    "내부 guard/retry/fallback 문구는 노출하지 않는다."
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
    _register_domain_reviewer(
        ctx,
        key=ACADEMY_REVIEWER_TASK,
        display_name="Miho academy governance reviewer",
        instructions=ACADEMY_REVIEWER_INSTRUCTIONS,
    )
    _register_domain_reviewer(
        ctx,
        key=DELIVERY_REVIEWER_TASK,
        display_name="Miho delivery governance reviewer",
        instructions=DELIVERY_REVIEWER_INSTRUCTIONS,
    )
    _register_domain_reviewer(
        ctx,
        key=DEV_REVIEWER_TASK,
        display_name="Miho dev governance reviewer",
        instructions=DEV_REVIEWER_INSTRUCTIONS,
    )
    _register_domain_reviewer(
        ctx,
        key=RESEARCH_REVIEWER_TASK,
        display_name="Miho research governance reviewer",
        instructions=RESEARCH_REVIEWER_INSTRUCTIONS,
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
    ctx.register_auxiliary_task(
        key=FINAL_DELIVERY_TASK,
        display_name="Miho governance final delivery agent",
        description="Decides and rewrites the final user-facing answer before delivery",
        defaults={
            "provider": "auto",
            "timeout": 30,
            "extra_body": {"reasoning": {"effort": "medium"}},
            "instructions": FINAL_DELIVERY_INSTRUCTIONS,
        },
    )
    _ensure_self_harness_autopilot_cron()


def _register_domain_reviewer(
    ctx: Any,
    *,
    key: str,
    display_name: str,
    instructions: str,
) -> None:
    ctx.register_auxiliary_task(
        key=key,
        display_name=display_name,
        description="Domain-specific LLM reviewer for governed Miho outputs",
        defaults={
            "provider": "auto",
            "timeout": 90,
            "extra_body": {"reasoning": {"effort": "medium"}},
            "instructions": instructions,
        },
    )


def _ensure_self_harness_autopilot_cron() -> None:
    """Idempotently schedule the unattended Self-Harness autopilot in production.

    Skipped under test/CI so plugin loading never writes a cron job there.
    """

    import os
    import sys

    if "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    if os.environ.get("MIHO_DISABLE_SELF_HARNESS_AUTOPILOT", "").strip().lower() in {
        "1",
        "true",
        "on",
        "yes",
    }:
        return
    try:
        from .self_harness_loop import register_self_harness_cron

        register_self_harness_cron()
    except Exception:  # cron infra optional; never block plugin load
        import logging

        logging.getLogger(__name__).debug("self-harness autopilot cron not registered", exc_info=True)


__all__ = [
    "ACADEMY_REVIEWER_TASK",
    "DELIVERY_REVIEWER_TASK",
    "DEV_REVIEWER_TASK",
    "DISPATCHER_TASK",
    "FINAL_DELIVERY_TASK",
    "FINAL_QA_REPAIR_TASK",
    "FINAL_QA_TASK",
    "PROMOTION_JUDGE_TASK",
    "RESEARCH_REVIEWER_TASK",
    "SELF_HARNESS_PROPOSER_TASK",
    "SELF_HARNESS_WEAKNESS_MINER_TASK",
    "governance_transform_llm_output",
    "REVIEWER_TASK",
    "register",
]
