"""Reviewer gate for sports performance feedback results."""

from __future__ import annotations

import json
import os
from typing import Any, Callable


REVIEWER_NAME = "sports_performance_reviewer"
_REVIEWED_TOOLS = {"sports_motion_feedback"}
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["pass", "fail"]},
        "errors": {"type": "array", "items": {"type": "string"}},
        "checked": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "errors", "checked"],
    "additionalProperties": False,
}


def make_result_review_hook(llm: Any = None) -> Callable[..., str | None]:
    def _hook(*, tool_name: Any = None, args: Any = None, result: Any = None, **_: Any) -> str | None:
        return review_tool_result(tool_name=tool_name, args=args, result=result, llm=llm)

    return _hook


def review_tool_result(*, tool_name: Any, args: Any, result: Any, llm: Any = None) -> str | None:
    del args
    if str(tool_name or "") not in _REVIEWED_TOOLS:
        return None
    payload = _loads_object(result)
    if payload is None or payload.get("ok") is not True or payload.get("reviewer"):
        return None
    errors = _check_feedback(payload)
    if errors:
        return _blocked(errors)
    retry = _retry_review(payload)
    if retry:
        payload["next_action"] = "retry_required"
        payload["delivery_status"] = "provisional"
        payload["retry_tools"] = retry["retry_tools"]
        payload["retry_args"] = retry["retry_args"]
        payload["reviewer"] = retry
        return json.dumps(payload, ensure_ascii=False)
    agent_review = _agent_review(llm, payload)
    if agent_review and agent_review["status"] == "fail":
        return _blocked(agent_review["errors"], checked=agent_review.get("checked") or _checked())
    payload["reviewer"] = {
        "name": REVIEWER_NAME,
        "status": "pass",
        "mode": agent_review["mode"] if agent_review else "deterministic_gate",
        "checked": agent_review["checked"] if agent_review else _checked(),
    }
    return json.dumps(payload, ensure_ascii=False)


def _check_feedback(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not str(payload.get("student_name") or "").strip():
        errors.append("학생명이 없다.")
    exercise = payload.get("exercise")
    if not isinstance(exercise, dict) or not exercise.get("key"):
        errors.append("종목 식별값이 없다.")
    if not isinstance(payload.get("normalized_metrics"), dict) or not payload.get("normalized_metrics"):
        errors.append("운동분석 지표가 없다.")
    output = payload.get("coach_output")
    if not isinstance(output, dict):
        errors.append("coach_output이 없다.")
        return errors
    for key, label in (
        ("bottlenecks", "병목"),
        ("technical_cues", "기술 큐"),
        ("drills", "드릴"),
        ("avoid", "금지/주의"),
    ):
        if not isinstance(output.get(key), list) or not output.get(key):
            errors.append(f"{label} 섹션이 비어 있다.")
    safety = payload.get("safety")
    if not isinstance(safety, dict) or not safety.get("status"):
        errors.append("안전 검수 상태가 없다.")
    if payload.get("evidence_status") not in {"pending_source_pack", "source_pack_linked"}:
        errors.append("근거 연결 상태가 올바르지 않다.")
    return errors


def _retry_review(payload: dict[str, Any]) -> dict[str, Any] | None:
    if payload.get("evidence_status") != "pending_source_pack":
        return None
    return {
        "name": REVIEWER_NAME,
        "status": "retry_needed",
        "mode": "deterministic_retry_gate",
        "checked": _checked(),
        "warnings": ["accepted PE-brain 근거팩이 없어 확정 처방이 아닌 가설형 피드백으로만 전달한다."],
        "retry_tools": ["sports_pe_brain_evidence", "sports_motion_feedback"],
        "retry_instruction_ko": "PE-brain 근거팩을 먼저 검색한 뒤 같은 운동 피드백 도구를 다시 실행해 주세요.",
        "retry_args": _retry_args(payload),
    }


def _retry_args(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_exercise = payload.get("exercise")
    exercise: dict[str, Any] = raw_exercise if isinstance(raw_exercise, dict) else {}
    return [
        {"tool": "sports_pe_brain_evidence", "args": {"exercise": exercise.get("key"), "limit": 5}},
        {
            "tool": "sports_motion_feedback",
            "args": {
                "student_name": payload.get("student_name"),
                "exercise": exercise.get("key"),
                "metrics": payload.get("normalized_metrics") or {},
                "records": payload.get("records") or {},
                "source": payload.get("source"),
                "measured_at": payload.get("measured_at"),
            },
        },
    ]


def _checked() -> list[str]:
    return ["학생/종목/지표", "기술 피드백 구조", "안전 문구", "논문 근거 연결 상태"]


def _blocked(errors: list[str], *, checked: list[str] | None = None) -> str:
    return json.dumps(
        {
            "ok": False,
            "errors": errors,
            "reviewer": {"name": REVIEWER_NAME, "status": "blocked", "checked": checked or _checked()},
            "assistant_guidance": "이 운동 피드백은 검수 실패다. 사용자에게 최종 처방처럼 전달하지 마라.",
        },
        ensure_ascii=False,
    )


def _agent_review(llm: Any, payload: dict[str, Any]) -> dict[str, Any] | None:
    if llm is None or os.environ.get("MIHO_SPORTS_PERFORMANCE_REVIEWER_LLM", "1").strip() == "0":
        return None
    try:
        response = llm.complete_structured(
            instructions=_review_instructions(),
            input=[{"type": "text", "text": json.dumps(payload, ensure_ascii=False)}],
            json_schema=REVIEW_SCHEMA,
            json_mode=True,
            schema_name="sports_performance_review",
            max_tokens=900,
            timeout=120,
            purpose=REVIEWER_NAME,
        )
        parsed = getattr(response, "parsed", None)
        if not isinstance(parsed, dict):
            return {"status": "fail", "errors": ["reviewer 에이전트가 JSON 판정을 반환하지 않았다."], "checked": _checked()}
        status = str(parsed.get("status") or "").strip()
        errors = [str(item) for item in parsed.get("errors") or [] if str(item).strip()]
        checked = [str(item) for item in parsed.get("checked") or [] if str(item).strip()] or _checked()
        if status == "fail":
            return {"status": "fail", "errors": errors or ["reviewer 에이전트가 실패로 판정했다."], "checked": checked}
        return {"status": "pass", "mode": "llm_subagent", "checked": checked}
    except Exception as exc:  # noqa: BLE001
        return {"status": "fail", "errors": [f"reviewer 에이전트 호출 실패: {type(exc).__name__}: {exc}"], "checked": _checked()}


def _review_instructions() -> str:
    return (
        "너는 체대입시 운동 피드백 reviewer 에이전트다. JSON만 반환한다. "
        "피드백이 입력 지표에 근거했는지, 통증 신호가 안전하게 처리됐는지, "
        "논문 근거가 없거나 PE-brain 근거팩이 accepted가 아닌데 확정 표현을 쓰지 않았는지, "
        "학생에게 위험한 처방이 없는지 검수한다."
    )


def _loads_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, dict) else None
