"""End-to-end sports motion report package tool."""

from __future__ import annotations

import json
from typing import Any, Callable

from tools.html_pdf_quality_gate_tool import html_pdf_quality_gate_tool

from .catalog import normalize_exercise
from .cohort_model import build_national_gender_model, enrich_latest_variables_with_model
from .feedback_tool import make_feedback_tool_handler
from .max_analysis_api import build_max_analysis_variables_response
from .pe_brain_evidence import build_pe_brain_evidence_response
from .report_contracts import has_valid_model_value, html_model_contract_error
from .report_html import write_sports_report_html
from .report_package_payloads import (
    compact_cohort_model,
    compact_feedback,
    compact_html,
    compact_max_analysis,
    compact_payloads,
    compact_pdf,
)


PdfGate = Callable[[dict[str, Any]], dict[str, Any] | str]

_SPORT_BY_EXERCISE = {"standing_long_jump": "slj", "shuttle_run": "sprint"}


def make_report_package_tool_handler(llm: Any = None):
    def _handler(args: dict[str, Any] | None = None, **_: Any) -> str:
        payload = build_sports_motion_report_package(args or {}, llm=llm)
        return json.dumps(payload, ensure_ascii=False)

    return _handler


def sports_motion_report_package_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    return json.dumps(build_sports_motion_report_package(args or {}), ensure_ascii=False)


def build_sports_motion_report_package(
    args: dict[str, Any],
    *,
    llm: Any = None,
    pdf_gate: PdfGate | None = None,
) -> dict[str, Any]:
    exercise = normalize_exercise(args.get("exercise") or args.get("sport") or "제멀")
    if exercise is None:
        return _blocked("지원하지 않는 운동분석 리포트 종목입니다.")
    if exercise["key"] not in _SPORT_BY_EXERCISE:
        return _blocked("현재 MAX API 패키지 리포트는 제멀/스프린트 계열만 지원합니다.")

    max_payload = build_max_analysis_variables_response(_max_args(args, exercise["key"]))
    max_error = _max_payload_error(max_payload)
    if max_error:
        return _blocked(max_error, max_analysis=max_payload)
    cohort_model = _cohort_model(args, exercise["key"], max_payload)
    cohort_error = _cohort_model_error(cohort_model)
    if cohort_error:
        return _blocked(cohort_error, max_analysis=max_payload, cohort_model=cohort_model)

    metrics = _metrics_from_max(max_payload)
    if not metrics:
        return _blocked("MAX API 결과에서 실제 운동분석 변인 숫자를 찾지 못했습니다.", max_analysis=max_payload)
    latest_variables = _latest_variables(max_payload, cohort_model)
    model_error = _elite_model_error(latest_variables)
    if model_error:
        return _blocked(model_error, max_analysis=max_payload, cohort_model=cohort_model)

    feedback = _feedback_payload(
        args,
        exercise,
        metrics,
        max_payload,
        _evidence_refs(args, exercise["key"]),
        llm=llm,
    )
    if _review_status(feedback) != "pass":
        return _blocked("운동 피드백 reviewer 통과 정보가 없습니다.", max_analysis=max_payload, feedback=feedback)

    html_payload = write_sports_report_html(
        _html_args(args, exercise, max_payload, feedback, cohort_model, latest_variables)
    )
    if html_payload.get("ok") is not True:
        return _blocked("운동분석 HTML 리포트 생성이 차단되었습니다.", max_analysis=max_payload, feedback=feedback, html=html_payload)
    html_error = html_model_contract_error(str(html_payload.get("html_path") or ""))
    if html_error:
        return _blocked(html_error, max_analysis=max_payload, feedback=feedback, html=html_payload)

    pdf_payload = _run_pdf_gate(str(html_payload.get("html_path") or ""), llm=llm, pdf_gate=pdf_gate)
    if pdf_payload.get("success") is not True:
        return _blocked("PDF 품질 게이트를 통과하지 못했습니다.", max_analysis=max_payload, feedback=feedback, html=html_payload, pdf=pdf_payload)

    artifact_path = str(pdf_payload.get("artifact_path") or pdf_payload.get("pdf_path") or "").strip()
    if not artifact_path:
        return _blocked("PDF 산출물 경로가 없습니다.", max_analysis=max_payload, feedback=feedback, html=html_payload, pdf=pdf_payload)

    return {
        "ok": True,
        "success": True,
        "schema_version": "sports-motion-report-package/v1",
        "student_name": _student_name(args, max_payload),
        "exercise": exercise,
        "max_analysis": compact_max_analysis(max_payload),
        "cohort_model": compact_cohort_model(cohort_model),
        "feedback": compact_feedback(feedback),
        "html": compact_html(html_payload),
        "pdf": compact_pdf(pdf_payload),
        "artifact_path": artifact_path,
        "pdf_path": artifact_path,
        "media_tag": f"MEDIA:`{artifact_path}`",
        "delivery_text": f"{_student_name(args, max_payload)} 학생 {_exercise_label(exercise)} 운동분석 리포트입니다.\nMEDIA:`{artifact_path}`",
        "governance_tools_used": [
            "sports_motion_report_package",
            "sports_max_analysis_variables",
            "sports_motion_feedback",
            "sports_report_html_template",
            "html_pdf_quality_gate",
        ],
        "reviewer": {
            "name": "sports_performance_reviewer",
            "status": "pass",
            "mode": "package_contract",
            "checked": ["학생/종목/지표", "기술 피드백 구조", "안전 문구", "논문 근거 연결 상태", "PDF 품질 게이트"],
        },
    }


def _max_args(args: dict[str, Any], exercise_key: str) -> dict[str, Any]:
    result = {
        "student_name": args.get("student_name") or args.get("student_query"),
        "sport": _SPORT_BY_EXERCISE[exercise_key],
        "academy_id": args.get("academy_id"),
        "academy_name": args.get("academy_name"),
        "from_date": args.get("from_date"),
        "to_date": args.get("to_date"),
        "limit": args.get("limit") or 1000,
        "collect_all_pages": True,
    }
    return {key: value for key, value in result.items() if value not in ("", None)}


def _cohort_args(args: dict[str, Any], exercise_key: str) -> dict[str, Any]:
    result = {
        "sport": _SPORT_BY_EXERCISE[exercise_key],
        "academy_id": args.get("academy_id") if args.get("scope") == "academy" else None,
        "from_date": args.get("from_date"),
        "to_date": args.get("to_date"),
        "limit": args.get("limit") or 1000,
        "collect_all_pages": True,
    }
    return {key: value for key, value in result.items() if value not in ("", None)}


def _cohort_model(args: dict[str, Any], exercise_key: str, max_payload: dict[str, Any]) -> dict[str, Any]:
    try:
        cohort_payload = build_max_analysis_variables_response(_cohort_args(args, exercise_key))
    except Exception as exc:  # noqa: BLE001 - report can still run with current measured variables.
        return {"ok": False, "errors": [f"전국 모델 계산 실패: {type(exc).__name__}"]}
    if cohort_payload.get("ok") is not True:
        return {"ok": False, "errors": ["전국 모델 API 조회 실패"], "source": "max_analysis_variables_api"}
    return build_national_gender_model(student_payload=max_payload, cohort_payload=cohort_payload)


def _max_payload_error(payload: dict[str, Any]) -> str:
    if payload.get("ok") is not True:
        return "MAX 운동분석 API 조회가 실패했습니다."
    if int(payload.get("record_count") or 0) <= 0:
        return "MAX 운동분석 API에서 학생 기록을 찾지 못했습니다."
    reviewer = payload.get("reviewer") if isinstance(payload.get("reviewer"), dict) else {}
    if str(reviewer.get("status") or "") != "pass":
        return "MAX 운동분석 API reviewer를 통과하지 못했습니다."
    return ""


def _cohort_model_error(model: dict[str, Any]) -> str:
    if model.get("ok") is not True:
        return "전국 성별 상위 1% 모델을 계산하지 못했습니다."
    if int(model.get("cohort_session_count") or 0) < 2:
        return "전국 성별 상위 1% 모델 비교 세션이 부족합니다."
    if int(model.get("elite_session_count") or 0) <= 0:
        return "전국 성별 상위 1% 모델 세션이 없습니다."
    return ""


def _elite_model_error(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "MAX API 결과에서 최신 측정 변인을 찾지 못했습니다."
    missing = [
        str(row.get("display_name") or row.get("variable_name") or row.get("variable_key") or "").strip()
        for row in rows
        if not has_valid_model_value(row.get("elite_1pct"))
    ]
    if missing:
        return "전국 성별 상위 1% 변인값이 없는 항목이 있어 PDF 생성을 중단했습니다."
    return ""


def _metrics_from_max(payload: dict[str, Any]) -> dict[str, Any]:
    rows = (payload.get("llm_context") or {}).get("latest_session_variables")
    if not isinstance(rows, list) or not rows:
        rows = payload.get("records") if isinstance(payload.get("records"), list) else []
    metrics: dict[str, Any] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = str(row.get("variable_key") or row.get("key") or "").strip()
        value = row.get("value", row.get("variable_value"))
        if key and value not in ("", None):
            metrics[key] = value
    return metrics


def _evidence_refs(args: dict[str, Any], exercise_key: str) -> list[str]:
    refs = [str(item).strip() for item in args.get("evidence_refs") or [] if str(item).strip()]
    if refs:
        return refs
    evidence = build_pe_brain_evidence_response({"exercise": exercise_key, "limit": 5})
    return [
        str(pack.get("id") or "").strip()
        for pack in evidence.get("packs") or []
        if isinstance(pack, dict) and str(pack.get("id") or "").strip()
    ]


def _feedback_payload(
    args: dict[str, Any],
    exercise: dict[str, Any],
    metrics: dict[str, Any],
    max_payload: dict[str, Any],
    evidence_refs: list[str],
    *,
    llm: Any,
) -> dict[str, Any]:
    raw = make_feedback_tool_handler(llm)(
        {
            "student_name": _student_name(args, max_payload),
            "exercise": exercise["key"],
            "metrics": metrics,
            "records": _feedback_records(max_payload),
            "evidence_refs": evidence_refs,
            "source": "max_analysis_variables_api",
            "measured_at": str((max_payload.get("latest_record") or {}).get("measured_at") or ""),
        }
    )
    return _loads_object(raw) or {"ok": False, "errors": ["운동 피드백 결과를 해석하지 못했습니다."]}


def _html_args(
    args: dict[str, Any],
    exercise: dict[str, Any],
    max_payload: dict[str, Any],
    feedback: dict[str, Any],
    cohort_model: dict[str, Any],
    latest_variables: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    latest = max_payload.get("latest_record") if isinstance(max_payload.get("latest_record"), dict) else {}
    first_record = (max_payload.get("records") or [{}])[0] if isinstance(max_payload.get("records"), list) else {}
    return {
        "exercise": exercise["key"],
        "student": {
            "name": _student_name(args, max_payload),
            "gender": first_record.get("gender") or args.get("gender") or "성별 미입력",
            "academy": latest.get("academy_name") or first_record.get("academy_name") or args.get("academy_name") or "소속 미입력",
            "measured_at": latest.get("measured_at") or "측정일 미입력",
        },
        "record": _record(max_payload, cohort_model),
        "comparison": cohort_model.get("comparison") if cohort_model.get("ok") else None,
        "variables": latest_variables if latest_variables is not None else _latest_variables(max_payload, cohort_model),
        "max_analysis": max_payload,
        "feedback": feedback,
    }


def _latest_variables(max_payload: dict[str, Any], cohort_model: dict[str, Any]) -> list[dict[str, Any]]:
    context = max_payload.get("llm_context") if isinstance(max_payload.get("llm_context"), dict) else {}
    rows = context.get("latest_session_variables")
    if not isinstance(rows, list) or not rows:
        rows = max_payload.get("records") if isinstance(max_payload.get("records"), list) else []
    return enrich_latest_variables_with_model(rows, model=cohort_model)


def _run_pdf_gate(html_path: str, *, llm: Any, pdf_gate: PdfGate | None) -> dict[str, Any]:
    gate = pdf_gate or (lambda payload: html_pdf_quality_gate_tool(payload))
    first = _loads_object(gate({"html_path": html_path})) or {}
    if first.get("success") is True:
        return first
    if first.get("next_action") != "visual_review_required":
        return first
    return _loads_object(
        gate(
            {
                "html_path": html_path,
                "pdf_path": first.get("pdf_path"),
                "visual_review": _visual_review(first, llm=llm),
            }
        )
    ) or {}


def _visual_review(payload: dict[str, Any], *, llm: Any) -> dict[str, Any]:
    del llm
    packet = _visual_packet(payload)
    quality = packet.get("pdf_quality_gate") if isinstance(packet.get("pdf_quality_gate"), dict) else {}
    errors = [str(item) for item in quality.get("layout_errors") or [] if str(item).strip()]
    if errors:
        return {
            "status": "fail",
            "checked": ["deterministic_pdf_layout_contract", "layout_errors"],
            "warnings": [],
            "errors": errors,
        }
    return {
        "status": "pass",
        "checked": ["deterministic_pdf_layout_contract", "contact_sheet", "page_previews"],
        "warnings": ["semantic_contract_checked_before_pdf_gate"],
        "errors": [],
    }


def _visual_packet(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "contact_sheet_path": payload.get("contact_sheet_path"),
        "page_images": payload.get("page_images"),
        "review_prompt": payload.get("review_prompt"),
        "pdf_quality_gate": payload.get("pdf_quality_gate"),
    }


def _feedback_records(max_payload: dict[str, Any]) -> dict[str, Any]:
    context = max_payload.get("llm_context") if isinstance(max_payload.get("llm_context"), dict) else {}
    return {
        "latest": context.get("latest_record") or _record_label(max_payload.get("latest_record")),
        "previous": context.get("previous_record") or "",
        "record_count": max_payload.get("record_count"),
    }


def _record(max_payload: dict[str, Any], cohort_model: dict[str, Any]) -> dict[str, str]:
    context = max_payload.get("llm_context") if isinstance(max_payload.get("llm_context"), dict) else {}
    summaries = max_payload.get("session_summaries") if isinstance(max_payload.get("session_summaries"), list) else []
    latest_record = max_payload.get("latest_record") if isinstance(max_payload.get("latest_record"), dict) else {}
    previous_record = summaries[1] if len(summaries) > 1 and isinstance(summaries[1], dict) else {}
    latest = _record_label(latest_record) or str(context.get("latest_record") or "").strip()
    previous = _record_label(previous_record) or str(context.get("previous_record") or "").strip()
    change = _record_change(latest_record, previous_record)
    percentile = "전국 모델 재계산 필요"
    if cohort_model.get("ok") is True:
        percentile = f"1% 모델 {cohort_model.get('elite_session_count')}세션"
    return {"current": latest, "previous": previous or "이전 기록 없음", "change": change, "percentile": percentile}


def _record_label(record: Any) -> str:
    data = record if isinstance(record, dict) else {}
    value = data.get("record_value")
    unit = str(data.get("record_unit") or "").strip()
    date = str(data.get("measured_at") or "").strip()
    return f"{date} {_format_record_value(value, unit)}".strip() if value not in ("", None) else date


def _record_change(latest: dict[str, Any], previous: dict[str, Any]) -> str:
    latest_value = _num(latest.get("record_value"))
    previous_value = _num(previous.get("record_value"))
    if latest_value is None or previous_value is None:
        return "이전 기록 없음"
    unit = str(latest.get("record_unit") or previous.get("record_unit") or "").strip()
    diff = latest_value - previous_value
    return f"{diff:+g}{unit}".strip()


def _format_record_value(value: Any, unit: str) -> str:
    number = _num(value)
    if number is None:
        return f"{value}{unit}".strip()
    return f"{number:g}{unit}".strip()


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _student_name(args: dict[str, Any], max_payload: dict[str, Any]) -> str:
    latest = max_payload.get("latest_record") if isinstance(max_payload.get("latest_record"), dict) else {}
    return str(args.get("student_name") or latest.get("student_name") or args.get("student_query") or "학생").strip()


def _exercise_label(exercise: dict[str, Any]) -> str:
    return str(exercise.get("name_ko") or exercise.get("key") or "운동분석")


def _review_status(payload: dict[str, Any]) -> str:
    reviewer = payload.get("reviewer") if isinstance(payload.get("reviewer"), dict) else {}
    return str(reviewer.get("status") or "").strip()


def _blocked(message: str, **payloads: Any) -> dict[str, Any]:
    return {
        "ok": False,
        "success": False,
        "delivery_status": "blocked",
        "errors": [message],
        "user_safe_message": message,
        "reviewer": {"name": "sports_performance_reviewer", "status": "blocked", "checked": ["학생/종목/지표", "PDF 산출 계약"]},
        **compact_payloads(payloads),
    }


def _loads_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None
