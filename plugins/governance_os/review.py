"""Generic review gate contracts for governed tool results."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from .registry import GovernanceRegistry


ReviewStatus = Literal["pass", "fail", "needs_human_review", "retry_needed"]
AuxiliaryReviewPolicy = Literal["auto", "always", "never"]

_REQUIRED_CHECKS_BY_GATE: dict[str, tuple[str, ...]] = {
    "dev_quality_review": ("tests", "rollback"),
    "source_attribution_review": ("source_attribution",),
    "attachment_delivery_review": ("media_tag", "artifact_path"),
    "memory_promotion_review": ("evidence", "privacy"),
}
_REQUIRED_CHECK_GROUPS_BY_GATE: dict[str, tuple[tuple[str, ...], ...]] = {
    "academy_result_reviewer": (
        ("내용", "근거", "요청 의도"),
        ("레이아웃", "산식"),
        ("PDF 이미지", "레이아웃"),
        ("필수 산출 필드", "상태값"),
        ("생기부 검수 상태", "사람 검수 필요 여부"),
    ),
}
_REVIEWER_TASK = "miho_governance_reviewer"
_ACADEMY_REVIEWER_TASK = "miho_governance_reviewer_academy"
_DELIVERY_REVIEWER_TASK = "miho_governance_reviewer_delivery"
_DEV_REVIEWER_TASK = "miho_governance_reviewer_dev"
_RESEARCH_REVIEWER_TASK = "miho_governance_reviewer_research"
_REVIEWER_TASK_BY_PLAYBOOK = {
    "academy_hakjong_report": _ACADEMY_REVIEWER_TASK,
    "academy_practical_recommendation": _ACADEMY_REVIEWER_TASK,
    "susi_score_calculation": _ACADEMY_REVIEWER_TASK,
    "life_record_ingest": _ACADEMY_REVIEWER_TASK,
    "discord_attachment_delivery": _DELIVERY_REVIEWER_TASK,
    "dev_code_update": _DEV_REVIEWER_TASK,
    "research_brief": _RESEARCH_REVIEWER_TASK,
}
_AUXILIARY_ALWAYS_PLAYBOOKS = frozenset(
    {
        "academy_hakjong_report",
        "academy_practical_recommendation",
        "susi_score_calculation",
        "life_record_ingest",
        "research_brief",
    }
)


@dataclass(frozen=True)
class ReviewGateOutcome:
    status: ReviewStatus
    reason: str
    message_ko: str = ""
    gate_names: tuple[str, ...] = field(default_factory=tuple)
    errors: tuple[str, ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    checked: tuple[str, ...] = field(default_factory=tuple)
    retry_tools: tuple[str, ...] = field(default_factory=tuple)
    retry_args: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    retry_instruction_ko: str = ""

    def __post_init__(self) -> None:
        if self.retry_tools and not self.retry_instruction_ko:
            object.__setattr__(self, "retry_instruction_ko", _retry_instruction_ko())


def evaluate_review_gate(
    registry: GovernanceRegistry,
    *,
    playbook_key: str,
    tool_name: str,
    result: Any,
    auxiliary_review_policy: AuxiliaryReviewPolicy = "auto",
) -> ReviewGateOutcome:
    playbook = registry.get_playbook(playbook_key)
    if tool_name not in playbook.required_tools or not playbook.review_gates:
        return ReviewGateOutcome(status="pass", reason="no_review_required")

    payload = _loads_object(result)
    if payload is None:
        return ReviewGateOutcome(
            status="fail",
            reason="result_not_json_object",
            message_ko="후검증 대상 결과를 읽을 수 없습니다. 같은 전용 도구를 다시 실행해야 합니다.",
            gate_names=playbook.review_gates,
            retry_tools=playbook.required_tools,
        )

    reviewer = payload.get("reviewer")
    if not isinstance(reviewer, dict):
        return ReviewGateOutcome(
            status="fail",
            reason="reviewer_missing",
            message_ko="후검증 정보가 없습니다. 결과를 전달하지 말고 같은 전용 도구를 다시 실행해야 합니다.",
            gate_names=playbook.review_gates,
            retry_tools=playbook.required_tools,
        )

    reviewer_name = str(reviewer.get("name") or "").strip()
    if reviewer_name and reviewer_name not in playbook.review_gates:
        return ReviewGateOutcome(
            status="fail",
            reason="reviewer_unexpected",
            message_ko="후검증 담당이 요청된 작업과 맞지 않습니다. 올바른 검수 도구로 다시 확인해야 합니다.",
            gate_names=(reviewer_name,),
            retry_tools=playbook.required_tools,
        )

    status = str(reviewer.get("status") or "").strip()
    gate_names = _gate_names(playbook.review_gates, reviewer)
    checked = _tuple_str(reviewer.get("checked"))
    if status == "pass":
        missing = _missing_required_checks(gate_names, checked)
        if missing:
            return ReviewGateOutcome(
                status="fail",
                reason="reviewer_missing_required_checks",
                message_ko=(
                    "필수 검수 항목이 빠졌습니다: "
                    + ", ".join(missing)
                    + ". 결과를 전달하지 말고 후검증을 다시 실행해야 합니다."
                ),
                gate_names=gate_names,
                checked=checked,
                retry_tools=playbook.required_tools,
            )
        if _auxiliary_review_required(
            policy=auxiliary_review_policy,
            payload=payload,
            reviewer=reviewer,
        ):
            return _evaluate_auxiliary_review(
                playbook_key=playbook_key,
                tool_name=tool_name,
                payload=payload,
                gate_names=gate_names,
                checked=checked,
                retry_tools=playbook.required_tools,
            )
        return ReviewGateOutcome(
            status="pass",
            reason="reviewer_pass",
            gate_names=gate_names,
            warnings=_tuple_str(reviewer.get("warnings")),
            checked=checked,
        )
    if status == "needs_human_review":
        return ReviewGateOutcome(
            status="needs_human_review",
            reason="reviewer_needs_human_review",
            message_ko="사람 검수가 필요한 결과입니다. 확정 표현 없이 원본 대조가 필요하다고 안내해야 합니다.",
            gate_names=gate_names,
            checked=checked,
        )
    if status == "retry_needed":
        return ReviewGateOutcome(
            status="retry_needed",
            reason="reviewer_retry_needed",
            message_ko=str(reviewer.get("retry_instruction_ko") or "").strip()
            or "후검증이 재실행을 요청했습니다. 확정 표현 없이 같은 작업을 다시 실행해야 합니다.",
            gate_names=gate_names,
            warnings=_tuple_str(reviewer.get("warnings")),
            checked=checked,
            retry_tools=_tuple_str(reviewer.get("retry_tools")) or playbook.required_tools,
            retry_args=_tuple_dict(reviewer.get("retry_args")),
        )
    if status in {"blocked", "fail", "failed"}:
        return ReviewGateOutcome(
            status="fail",
            reason="reviewer_failed",
            message_ko="후검증이 결과 전달을 막았습니다. 오류를 고친 뒤 같은 전용 도구를 다시 실행해야 합니다.",
            gate_names=gate_names,
            errors=_tuple_str(payload.get("errors")),
            warnings=_tuple_str(payload.get("warnings")),
            checked=checked,
            retry_tools=playbook.required_tools,
        )
    return ReviewGateOutcome(
        status="fail",
        reason="reviewer_unknown_status",
        message_ko="후검증 상태를 확인할 수 없습니다. 결과를 전달하지 말고 다시 검증해야 합니다.",
        gate_names=gate_names,
        retry_tools=playbook.required_tools,
    )


def auxiliary_review_policy_for_playbook(playbook_key: str) -> AuxiliaryReviewPolicy:
    if str(playbook_key or "") in _AUXILIARY_ALWAYS_PLAYBOOKS:
        return "always"
    return "auto"


def reviewer_task_for_playbook(playbook_key: str) -> str:
    return _REVIEWER_TASK_BY_PLAYBOOK.get(str(playbook_key or ""), _REVIEWER_TASK)


def _loads_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _auxiliary_review_required(
    *,
    policy: AuxiliaryReviewPolicy,
    payload: dict[str, Any],
    reviewer: dict[str, Any],
) -> bool:
    if policy == "always":
        return True
    if policy == "never":
        return False
    return _semantic_review_required(payload, reviewer)


def _semantic_review_required(payload: dict[str, Any], reviewer: dict[str, Any]) -> bool:
    values = (
        payload.get("semantic_review_required"),
        reviewer.get("semantic_review_required"),
        payload.get("semantic_risk"),
        reviewer.get("semantic_risk"),
    )
    return any(_truthy_semantic_flag(value) for value in values)


def _truthy_semantic_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().casefold()
    return text in {"1", "true", "yes", "y", "high", "medium", "required"}


def _evaluate_auxiliary_review(
    *,
    playbook_key: str,
    tool_name: str,
    payload: dict[str, Any],
    gate_names: tuple[str, ...],
    checked: tuple[str, ...],
    retry_tools: tuple[str, ...],
) -> ReviewGateOutcome:
    try:
        result = _call_auxiliary_reviewer(
            task=reviewer_task_for_playbook(playbook_key),
            playbook_key=playbook_key,
            tool_name=tool_name,
            payload=payload,
            gate_names=gate_names,
            checked=checked,
        )
    except Exception:
        return ReviewGateOutcome(
            status="fail",
            reason="auxiliary_reviewer_unavailable",
            message_ko="의미 검증을 완료하지 못했습니다. 결과를 확정하지 말고 전용 도구를 다시 실행해야 합니다.",
            gate_names=gate_names,
            checked=checked,
            retry_tools=retry_tools,
        )
    return _outcome_from_auxiliary_review(
        result,
        gate_names=gate_names,
        checked=checked,
        retry_tools=retry_tools,
    )


def _call_auxiliary_reviewer(
    *,
    task: str,
    playbook_key: str,
    tool_name: str,
    payload: dict[str, Any],
    gate_names: tuple[str, ...],
    checked: tuple[str, ...],
    call_llm: Callable[..., Any] | None = None,
    extract_content: Callable[[Any], Any] | None = None,
) -> dict[str, Any]:
    if call_llm is None or extract_content is None:
        from agent.auxiliary_client import call_llm as default_call_llm
        from agent.auxiliary_client import extract_content_or_reasoning

        call = default_call_llm if call_llm is None else call_llm
        extract = extract_content_or_reasoning if extract_content is None else extract_content
    else:
        call = call_llm
        extract = extract_content

    response = call(
        task=task,
        messages=[
            {
                "role": "system",
                "content": (
                    "Return JSON only. Review whether the governed tool result can be delivered. "
                    "Use status pass, fail, needs_human_review, or retry_needed."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "playbook_key": playbook_key,
                        "tool_name": tool_name,
                        "gate_names": list(gate_names),
                        "checked": list(checked),
                        "payload": payload,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        temperature=0,
        max_tokens=500,
        timeout=15,
    )
    parsed = _loads_object(extract(response))
    if parsed is None:
        raise ValueError("auxiliary reviewer returned invalid JSON")
    return parsed


def _outcome_from_auxiliary_review(
    result: dict[str, Any],
    *,
    gate_names: tuple[str, ...],
    checked: tuple[str, ...],
    retry_tools: tuple[str, ...],
) -> ReviewGateOutcome:
    status = str(result.get("status") or "").strip()
    aux_checked = _tuple_str(result.get("checked")) or checked
    message = str(result.get("message_ko") or "").strip()
    if status == "pass":
        return ReviewGateOutcome(
            status="pass",
            reason="auxiliary_reviewer_pass",
            gate_names=gate_names,
            warnings=_tuple_str(result.get("warnings")),
            checked=aux_checked,
        )
    if status == "needs_human_review":
        return ReviewGateOutcome(
            status="needs_human_review",
            reason="auxiliary_reviewer_needs_human_review",
            message_ko=message or "의미 검증 결과 사람 검수가 필요합니다. 확정 표현 없이 안내해야 합니다.",
            gate_names=gate_names,
            checked=aux_checked,
        )
    if status == "retry_needed":
        return ReviewGateOutcome(
            status="retry_needed",
            reason="auxiliary_reviewer_retry_needed",
            message_ko=message or "의미 검증이 재실행을 요청했습니다. 확정 표현 없이 다시 실행해야 합니다.",
            gate_names=gate_names,
            warnings=_tuple_str(result.get("warnings")),
            checked=aux_checked,
            retry_tools=_tuple_str(result.get("retry_tools")) or retry_tools,
            retry_args=_tuple_dict(result.get("retry_args")),
        )
    return ReviewGateOutcome(
        status="fail",
        reason="auxiliary_reviewer_failed",
        message_ko=message or "의미 검증이 결과 전달을 막았습니다. 오류를 고친 뒤 다시 검증해야 합니다.",
        gate_names=gate_names,
        errors=_tuple_str(result.get("errors")),
        warnings=_tuple_str(result.get("warnings")),
        checked=aux_checked,
        retry_tools=retry_tools,
        retry_args=_tuple_dict(result.get("retry_args")),
    )


def _gate_names(expected: tuple[str, ...], reviewer: dict[str, Any]) -> tuple[str, ...]:
    name = str(reviewer.get("name") or "").strip()
    return (name,) if name else expected


def _missing_required_checks(
    gate_names: tuple[str, ...],
    checked: tuple[str, ...],
) -> tuple[str, ...]:
    checked_set = {item.casefold() for item in checked}
    missing: list[str] = []
    for gate_name in gate_names:
        for required in _REQUIRED_CHECKS_BY_GATE.get(gate_name, ()):
            if required.casefold() not in checked_set:
                missing.append(required)
        groups = _REQUIRED_CHECK_GROUPS_BY_GATE.get(gate_name, ())
        if groups and not any(_group_satisfied(group, checked_set) for group in groups):
            missing.append(f"{gate_name}: meaningful checked items")
    return tuple(missing)


def _group_satisfied(group: tuple[str, ...], checked_set: set[str]) -> bool:
    return all(item.casefold() in checked_set for item in group)


def _retry_instruction_ko() -> str:
    return "결과를 전달하지 말고 같은 작업을 전용 도구로 다시 실행해 주세요."


def _tuple_str(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _tuple_dict(value: Any) -> tuple[dict[str, Any], ...]:
    if isinstance(value, dict):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(item for item in value if isinstance(item, dict))
    return ()
