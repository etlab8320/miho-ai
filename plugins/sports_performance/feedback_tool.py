"""Sports motion feedback tool."""

from __future__ import annotations

import json
import os
from typing import Any

from .catalog import EXERCISES, normalize_exercise, normalize_metrics, schema_payload
from .pe_brain_evidence import resolve_pe_brain_evidence_refs

COACH_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "bottlenecks": {"type": "array", "items": {"type": "string"}},
        "technical_cues": {"type": "array", "items": {"type": "string"}},
        "drills": {"type": "array", "items": {"type": "string"}},
        "one_week_plan": {"type": "array", "items": {"type": "string"}},
        "avoid": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "bottlenecks", "technical_cues", "drills", "one_week_plan", "avoid"],
    "additionalProperties": True,
}


def schema_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    del args
    return json.dumps(schema_payload(), ensure_ascii=False)


def make_feedback_tool_handler(llm: Any = None):
    def _handler(args: dict[str, Any] | None = None, **_: Any) -> str:
        clean_args = args or {}
        payload = build_feedback(clean_args, llm=llm)
        raw = json.dumps(payload, ensure_ascii=False)
        if payload.get("ok") is not True:
            return raw
        from .result_reviewer import review_tool_result

        return review_tool_result(
            tool_name="sports_motion_feedback",
            args=clean_args,
            result=raw,
            llm=llm,
        ) or raw

    return _handler


def feedback_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = build_feedback(args or {}, llm=None)
    return json.dumps(payload, ensure_ascii=False)


def build_feedback(args: dict[str, Any], *, llm: Any = None) -> dict[str, Any]:
    student_name = str(args.get("student_name") or args.get("student_query") or "학생").strip()
    exercise = normalize_exercise(args.get("exercise"))
    if exercise is None:
        return {"ok": False, "errors": ["지원하지 않는 종목이다. sports_motion_schema로 종목명을 확인해라."]}
    metrics = normalize_metrics(exercise["key"], args.get("metrics"))
    if not metrics:
        return {"ok": False, "errors": ["metrics가 필요하다. 업체 API/PDF 파싱값 또는 수동 지표를 넣어야 한다."]}

    pain_flags = [str(item).strip() for item in args.get("pain_flags") or [] if str(item).strip()]
    evidence_refs = [str(item).strip() for item in args.get("evidence_refs") or [] if str(item).strip()]
    evidence_validation = resolve_pe_brain_evidence_refs(evidence_refs, exercise_key=exercise["key"])
    usable_evidence_refs = evidence_validation["accepted_refs"]
    safety = _safety(pain_flags)
    evidence_status = _evidence_status(evidence_refs, evidence_validation)
    if evidence_status == "source_pack_linked":
        coach_output, coach_agent = _coach_output_with_agent(
            llm=llm,
            exercise_key=exercise["key"],
            exercise=exercise,
            metrics=metrics,
            records=args.get("records") or {},
            pain_flags=pain_flags,
            evidence_refs=usable_evidence_refs,
            safety=safety,
        )
    else:
        coach_output = _coach_output(exercise["key"], metrics, pain_flags)
        coach_agent = {
            "name": "sports_performance_coach",
            "status": "skipped",
            "mode": "deterministic_pending_evidence",
        }
    return {
        "ok": True,
        "schema_version": 1,
        "student_name": student_name,
        "exercise": exercise,
        "source": str(args.get("source") or "manual_or_vendor_pending"),
        "measured_at": str(args.get("measured_at") or ""),
        "records": args.get("records") or {},
        "normalized_metrics": metrics,
        "safety": safety,
        "evidence_status": evidence_status,
        "evidence_refs": usable_evidence_refs,
        "evidence_validation": evidence_validation,
        "evidence_packs": evidence_validation["accepted_packs"],
        "evidence_note": _evidence_note(evidence_refs, evidence_validation),
        "coach_agent": coach_agent,
        "coach_output": coach_output,
    }


def _coach_output_with_agent(
    *,
    llm: Any,
    exercise_key: str,
    exercise: dict[str, Any],
    metrics: dict[str, Any],
    records: dict[str, Any],
    pain_flags: list[str],
    evidence_refs: list[str],
    safety: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    fallback = _coach_output(exercise_key, metrics, pain_flags)
    if llm is None or os.environ.get("MIHO_SPORTS_PERFORMANCE_COACH_LLM", "1").strip() == "0":
        return fallback, {"name": "sports_performance_coach", "status": "fallback", "mode": "deterministic"}
    packet = {
        "exercise": exercise,
        "metrics": metrics,
        "records": records,
        "pain_flags": pain_flags,
        "safety": safety,
        "evidence_refs": evidence_refs,
        "fallback": fallback,
    }
    try:
        response = llm.complete_structured(
            instructions=_coach_instructions(),
            input=[{"type": "text", "text": json.dumps(packet, ensure_ascii=False)}],
            json_schema=COACH_SCHEMA,
            json_mode=True,
            schema_name="sports_performance_coach",
            max_tokens=1400,
            timeout=120,
            purpose="sports_performance_coach",
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, dict) and _valid_coach_output(parsed):
            return parsed, {"name": "sports_performance_coach", "status": "pass", "mode": "llm_subagent"}
    except Exception as exc:  # noqa: BLE001
        return fallback, {
            "name": "sports_performance_coach",
            "status": "fallback",
            "mode": "deterministic_after_agent_error",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return fallback, {"name": "sports_performance_coach", "status": "fallback", "mode": "invalid_agent_output"}


def _coach_output(exercise_key: str, metrics: dict[str, Any], pain_flags: list[str]) -> dict[str, Any]:
    exercise = EXERCISES[exercise_key]
    bottlenecks = _bottlenecks(exercise_key, metrics)
    avoid = [
        "통증·저림·불안정감이 있으면 반복 측정과 고강도 훈련을 중단하고 현장 지도자 확인을 먼저 한다."
    ] if pain_flags else ["영상/측정값만으로 최대강도 처방을 확정하지 않는다."]
    return {
        "summary": f"{exercise['name_ko']} 분석값을 기준으로 병목 후보를 정리했다.",
        "bottlenecks": bottlenecks,
        "technical_cues": [f"{point}를 영상 기준으로 다시 확인한다." for point in exercise["checkpoints"][:3]],
        "drills": list(exercise["drills"]),
        "one_week_plan": [
            "1일차: 기술 드릴과 낮은 강도 반복",
            "2일차: 보강운동과 가동성",
            "3일차: 재측정 전 짧은 품질 반복",
        ],
        "avoid": avoid,
        "review_required": ["sports_performance_reviewer", "human_coach_if_pain"],
    }


def _bottlenecks(exercise_key: str, metrics: dict[str, Any]) -> list[str]:
    items: list[str] = []
    if exercise_key == "standing_long_jump":
        takeoff_angle = _metric_num(metrics, "takeoff_angle", "launch_angle", default=99)
        horizontal_velocity = _metric_num(metrics, "horizontal_velocity", default=99)
        transition_time = _metric_num(metrics, "takeoff_transition_time", default=0)
        if takeoff_angle < 23:
            items.append("이륙각이 낮아 수평속도 대비 체공 성분이 부족할 수 있다.")
        if horizontal_velocity < 4.0:
            items.append("수평속도가 낮아 앞으로 미는 힘이 기록으로 충분히 연결되지 않는다.")
        if transition_time > 0.35:
            items.append("전환시간이 길어 앉은 뒤 바로 밀고 나오는 반동 활용이 늦다.")
    if exercise_key == "medicine_ball_throw" and _num(metrics.get("trunk_rotation"), 99) < 35:
        items.append("몸통 회전 기여가 낮아 팔 위주 투척으로 흐를 수 있다.")
    if exercise_key == "shuttle_run" and _num(metrics.get("contact_time"), 0) > 0.35:
        items.append("방향전환 접지 시간이 길어 재가속이 늦어질 수 있다.")
    if exercise_key == "back_strength" and str(metrics.get("scapular_set") or "") in {"false", "불안정"}:
        items.append("견갑/몸통 고정이 흔들리면 허리 보상 사용이 커질 수 있다.")
    if exercise_key == "sit_and_reach" and str(metrics.get("asymmetry") or "") in {"true", "있음", "불안정"}:
        items.append("좌우 비대칭이 있으면 단순 전굴 반복보다 원인 확인이 먼저다.")
    return items or ["현재 지표만으로는 단일 병목을 확정하지 않고 종목 체크포인트별 재확인이 필요하다."]


def _safety(pain_flags: list[str]) -> dict[str, Any]:
    if pain_flags:
        return {
            "status": "needs_human_check",
            "flags": pain_flags,
            "message": "통증 신호가 있어 고강도 처방 전 현장 지도자 또는 의료 전문가 확인이 필요하다.",
        }
    return {"status": "ok", "flags": [], "message": "통증 신호 입력 없음. 그래도 영상만으로 의료 판단은 하지 않는다."}


def _evidence_status(evidence_refs: list[str], validation: dict[str, Any]) -> str:
    if not evidence_refs:
        return "pending_source_pack"
    if validation["accepted_refs"]:
        return "source_pack_linked"
    return "pending_source_pack"


def _evidence_note(evidence_refs: list[str], validation: dict[str, Any]) -> str:
    if not evidence_refs:
        return "논문팩 연결 전 임시 코칭이다. 최종 처방 전 종목별 논문/근거팩을 연결해야 한다."
    if validation["invalid_refs"]:
        return "제공된 PE-brain 근거팩은 제외했다. 근거 확정 전 가설형 분석과 다음 훈련안을 제공한다."
    return "검증된 evidence_refs 기준으로 근거를 연결했다."


def _num(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _metric_num(metrics: dict[str, Any], *keys: str, default: float) -> float:
    for key in keys:
        if key in metrics:
            return _num(metrics.get(key), default)
    return default


def _valid_coach_output(output: dict[str, Any]) -> bool:
    required = ("summary", "bottlenecks", "technical_cues", "drills", "one_week_plan", "avoid")
    return all(isinstance(output.get(key), list) and output[key] for key in required if key != "summary") and bool(
        str(output.get("summary") or "").strip()
    )


def _coach_instructions() -> str:
    return (
        "너는 체대입시 운동분석 코치 에이전트다. JSON만 반환한다. "
        "Python fallback 문구를 그대로 복붙하지 말고, 입력 지표와 학생 기록을 보고 종목별 병목·기술 큐·드릴을 작성한다. "
        "논문 evidence_refs가 없으면 근거를 확정한 척하지 말고 '근거팩 연결 전 가설'로 표현한다. "
        "통증 신호가 있으면 고강도 처방을 금지하고 현장 지도자/의료 확인을 우선한다."
    )
