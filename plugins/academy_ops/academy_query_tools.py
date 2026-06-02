"""Read-only PACA/Peak tools and guarded write drafts."""

from __future__ import annotations

from datetime import date, timedelta
import json
from typing import Any

from .academy_api import AcademyApiClient, AcademyApiError
from .auth_store import decrypt_token, get_binding
from .catalog import OperationSpec, find_operation
from .consultation_candidate_format import consultation_candidates_message
from .consultation_candidate_renderer import (
    ConsultationCandidateImageRenderer,
    ConsultationCandidateRenderError,
)
from .attendance_day_image_payload import with_attendance_day_image
from .context import current_discord_user_id
from .plan_lookup import plan_lookup_for_day
from .response_guidance import academy_response_guidance
from .student_card import AcademyClient, AcademyStudentCardService, StudentCardError
from .token_metadata import binding_token_error


def _capability_status_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    operation_key = str((args or {}).get("operation_key") or "").strip()
    if not operation_key:
        return _json_error("확인할 학원 업무 키를 operation_key로 지정해줘.")
    op = find_operation(operation_key)
    if op is None:
        return _json_error("요청을 처리할 학원 업무를 찾지 못했어.")
    return _json_ok(
        {
            "operation": "capability.status",
            "operation_key": op.key,
            "title": op.title,
            "domain": op.domain,
            "mode": op.mode,
            "implementation_status": op.implementation_status,
            "api_contract_status": op.api_contract_status,
            "can_execute_now": _can_execute_now(op),
            "recommended_tool": _recommended_tool(op),
            "message": _capability_message(op),
        }
    )


def _student_summary_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    query = str(payload.get("student_query") or "").strip()
    if not query:
        return _json_error("학생 이름이나 검색어를 알려줘.")
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        card = AcademyStudentCardService(client_or_error).build(
            query,
            today=_date_arg(payload.get("today")),
            period_days=_int_arg(payload.get("period_days"), default=14, maximum=60),
        )
    except (AcademyApiError, StudentCardError) as exc:
        return _json_error(str(exc))
    return _json_ok(
        {
            "operation": "student.summary",
            "message": f"{card.profile.name} 학생 요약을 실제 조회 데이터로 정리했어.",
            "card": card.to_public_dict(),
            "assistant_guidance": _assistant_guidance(),
        }
    )


def _attendance_day_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    target_day = _date_arg(payload.get("date"))
    if target_day is None:
        return _json_error("조회 날짜를 YYYY-MM-DD로 지정해줘.")
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        attendance = client_or_error.get_peak_attendance(target_day)
    except AcademyApiError as exc:
        return _json_error(str(exc))
    slots, summary = _safe_attendance_slots(attendance)
    result = {
        "operation": "attendance.day",
        "date": target_day.isoformat(),
        "summary": summary,
        "slots": slots,
        "message": _attendance_message(target_day, summary),
        "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
    }
    if bool(payload.get("image")):
        result = with_attendance_day_image(result, kwargs.get("renderer"))
    return _json_ok(result)


def _plan_by_date_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    target_day = _date_arg(payload.get("date"))
    if target_day is None:
        return _json_error("조회 날짜를 YYYY-MM-DD로 지정해줘.")
    trainer_query = str(payload.get("trainer_query") or "").strip()
    time_slot = str(payload.get("time_slot") or "").strip()
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        plans = plan_lookup_for_day(
            client_or_error,
            target_day,
            trainer_query=trainer_query,
            time_slot=time_slot,
        )
    except AcademyApiError as exc:
        return _json_error(str(exc))
    return _json_ok(
        {
            "operation": "plan.by_date",
            "date": plans["date"],
            "trainer_query": trainer_query,
            "time_slot": time_slot,
            "summary": plans["summary"],
            "plans": plans["plans"],
            "message": _plan_message(plans),
            "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
        }
    )


def _consultation_candidates_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    target_day = _date_arg(payload.get("today")) or date.today()
    period_days = _int_arg(payload.get("period_days"), default=14, maximum=30)
    limit = _int_arg(payload.get("limit"), default=10, maximum=30)
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        server_lookup = getattr(client_or_error, "get_consultation_candidates", None)
        if callable(server_lookup):
            result = server_lookup(today=target_day, attendance_days=period_days, limit=limit)
            payload = _server_consultation_candidates_payload(result, target_day, period_days)
            return _json_ok(_with_consultation_candidate_image(payload, kwargs.get("renderer")))
        candidates = _consultation_candidates(client_or_error, target_day, period_days, limit)
    except AcademyApiError as exc:
        return _json_error(str(exc))
    payload = {
        "operation": "consultation.candidates",
        "period_days": period_days,
        "today": target_day.isoformat(),
        "write_enabled": False,
        "basis": "최근 출결만 사용한 읽기 전용 후보 목록이야. 결제/상담 메모는 아직 섞지 않았어.",
        "candidates": candidates,
        "message": consultation_candidates_message(candidates, period_days),
        "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
    }
    return _json_ok(_with_consultation_candidate_image(payload, kwargs.get("renderer")))


def _server_consultation_candidates_payload(
    result: dict[str, Any],
    target_day: date,
    period_days: int,
) -> dict[str, Any]:
    candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
    return {
        "operation": "consultation.candidates",
        "period_days": period_days,
        "today": target_day.isoformat(),
        "write_enabled": False,
        "basis": f"PACA 서버가 최근 {period_days}일 출결과 Peak 최근 5개 기록을 조합한 읽기 전용 후보 목록이야.",
        "period": result.get("period") if isinstance(result.get("period"), dict) else {},
        "policy": result.get("policy") if isinstance(result.get("policy"), dict) else {},
        "candidates": [item for item in candidates if isinstance(item, dict)],
        "message": consultation_candidates_message(candidates, period_days),
        "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
    }


def _with_consultation_candidate_image(
    payload: dict[str, Any],
    renderer: Any = None,
) -> dict[str, Any]:
    candidates = [item for item in payload.get("candidates") or [] if isinstance(item, dict)]
    if not candidates:
        return payload
    active_renderer = renderer or ConsultationCandidateImageRenderer()
    try:
        image_path = active_renderer.render(payload)
    except ConsultationCandidateRenderError as exc:
        enriched = dict(payload)
        enriched["image_error"] = str(exc)
        enriched["message"] = (
            "상담 후보 목록은 조회했지만 이미지 파일 생성에 실패했어. "
            "아래 텍스트로 먼저 확인해줘.\n"
            f"{payload.get('message', '')}"
        ).strip()
        return enriched
    enriched = dict(payload)
    media_tag = f"MEDIA:{image_path}"
    enriched["image_path"] = str(image_path)
    enriched["media_tag"] = media_tag
    enriched["message"] = f"{payload.get('message', '')}\n{media_tag}".strip()
    return enriched


def _write_action_draft_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    operation_key = str(payload.get("operation_key") or "").strip()
    if not operation_key:
        return _json_error("반영하려는 학원 업무 키를 operation_key로 지정해줘.")
    op = find_operation(operation_key)
    if op is None:
        return _json_error("요청을 처리할 학원 업무를 찾지 못했어.")
    fields = _confirmation_fields(op.domain)
    return _json_ok(
        {
            "operation": "write.action_draft",
            "operation_key": op.key,
            "title": op.title,
            "mode": op.mode,
            "can_execute": False,
            "requires_confirmation": bool(op.requires_confirmation),
            "requires_audit_log": bool(op.requires_audit_log),
            "blocked_reason": "쓰기 작업은 Discord 확인 버튼과 감사 로그가 붙기 전까지 실행하지 않아.",
            "confirmation_fields": fields,
            "audit_preview": {
                "request": str(payload.get("request") or ""),
                "operation_key": op.key,
                "status": "draft_only",
            },
            "message": "쓰기 작업은 아직 초안만 만들고 실제 반영은 하지 않아.",
        }
    )


def _consultation_candidates(
    client: AcademyClient,
    today: date,
    period_days: int,
    limit: int,
) -> list[dict[str, Any]]:
    students = {
        _to_int(row.get("id")): {
            "student_id": _to_int(row.get("id")),
            "name": str(row.get("name") or "이름 없음"),
            "school": str(row.get("school") or ""),
            "grade": str(row.get("grade") or ""),
            "signals": {"present": 0, "late": 0, "absent": 0, "unknown": 0},
            "recent_absences": [],
        }
        for row in client.list_peak_students()
        if _to_int(row.get("id"))
    }
    first_day = today - timedelta(days=period_days - 1)
    for offset in range(period_days):
        day = first_day + timedelta(days=offset)
        payload = client.get_peak_attendance(day)
        seen = set()
        for row in _iter_attendance_rows(payload):
            student_id = _to_int(row.get("student_id"))
            if student_id not in students:
                continue
            seen.add(student_id)
            status = _attendance_status(row)
            bucket = status if status in {"present", "late", "absent"} else "unknown"
            students[student_id]["signals"][bucket] += 1
            if bucket == "absent":
                students[student_id]["recent_absences"].append(day.isoformat())
        for student_id, item in students.items():
            if student_id not in seen:
                item["signals"]["unknown"] += 1
    candidates = [_candidate_item(item, period_days) for item in students.values()]
    candidates = [item for item in candidates if item["score"] > 0]
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]


def _candidate_item(item: dict[str, Any], period_days: int) -> dict[str, Any]:
    signals = item["signals"]
    absent = int(signals["absent"])
    late = int(signals["late"])
    unknown = int(signals["unknown"])
    present_like = int(signals["present"]) + late
    marked = max(1, period_days - unknown)
    rate = present_like / marked
    score = (absent * 3) + late + (2 if marked >= 4 and rate < 0.8 else 0)
    reasons = []
    if absent >= 2:
        reasons.append(f"최근 결석 {absent}회")
    if late >= 2:
        reasons.append(f"최근 지각 {late}회")
    if marked >= 4 and rate < 0.8:
        reasons.append(f"등원률 {round(rate * 100)}%")
    return {
        "student_id": item["student_id"],
        "name": item["name"],
        "school": item["school"],
        "grade": item["grade"],
        "score": score,
        "signals": dict(signals),
        "recent_absences": list(item["recent_absences"][-5:]),
        "reasons": reasons,
    }


def _safe_attendance_slots(payload: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    slots: dict[str, list[dict[str, Any]]] = {}
    summary = {"present": 0, "late": 0, "absent": 0, "unknown": 0}
    for slot, rows in _slot_rows(payload):
        safe_rows = []
        for row in rows:
            status = _attendance_status(row)
            bucket = status if status in {"present", "late", "absent"} else "unknown"
            summary[bucket] += 1
            safe_rows.append(
                {
                    "student_id": _to_int(row.get("student_id")),
                    "name": str(row.get("name") or row.get("student_name") or ""),
                    "school": str(row.get("school") or ""),
                    "grade": str(row.get("grade") or ""),
                    "attendance_status": bucket,
                }
            )
        slots[slot] = safe_rows
    return slots, summary


def _iter_attendance_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _slot, slot_rows in _slot_rows(payload):
        rows.extend(slot_rows)
    return rows


def _slot_rows(payload: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    slots = payload.get("slots") if isinstance(payload, dict) else {}
    if not isinstance(slots, dict):
        return []
    result = []
    for slot, rows in slots.items():
        if isinstance(rows, list):
            result.append((str(slot), [row for row in rows if isinstance(row, dict)]))
    return result


def _resolve_client(injected: Any = None) -> AcademyClient | str:
    if injected is not None:
        return injected
    discord_user_id = current_discord_user_id()
    if not discord_user_id:
        return "디스코드 사용자 정보를 확인하지 못했어. 디스코드에서 다시 요청해줘."
    binding = get_binding(discord_user_id)
    if binding is None:
        return "학원 계정 연결이 필요해. `/academy login`으로 먼저 연결해줘."
    token = decrypt_token(binding.token_ciphertext) or ""
    if not token:
        return "학원 계정 연결을 복호화하지 못했어. `/academy login`으로 다시 연결해줘."
    token_error = binding_token_error(token, academy_id=binding.academy_id)
    if token_error:
        return token_error
    try:
        return AcademyApiClient(token=token)
    except AcademyApiError as exc:
        return str(exc)


def _assistant_guidance() -> dict[str, Any]:
    guidance = academy_response_guidance()
    guidance["use_fields"] = ["card.risk", "card.attendance", "card.records", "card.missing_sources"]
    return guidance


def _can_execute_now(op: OperationSpec) -> bool:
    return op.implementation_status == "implemented" and op.api_contract_status == "verified_in_plugin"


def _recommended_tool(op: OperationSpec) -> str | None:
    if op.key == "attendance.today_peak":
        return "academy_attendance_day"
    if op.key == "attendance.student_month":
        return "academy_student_attendance_range"
    if op.key in {"student.search", "student.detail", "peak.records.latest"}:
        return "academy_student_summary"
    if op.key == "consultation.candidates":
        return "academy_consultation_candidates"
    if op.key == "staff.attendance_day":
        return "academy_staff_attendance_day"
    if op.key == "staff.schedule_day":
        return "academy_staff_schedule_day"
    if op.key == "plan.by_date":
        return "academy_plan_by_date"
    if op.key == "assignment.by_date":
        return "academy_assignment_by_date"
    return None


def _capability_message(op: OperationSpec) -> str:
    if _can_execute_now(op):
        tool = _recommended_tool(op)
        if tool:
            return f"{op.title}은 현재 연결된 도구로 조회할 수 있어. `{tool}`을 사용해."
        return f"{op.title}은 현재 연결된 기능이야."
    return f"{op.title}은 아직 연동 후보라서 실제 데이터로 처리하면 안 돼."


def _plan_message(payload: dict[str, Any]) -> str:
    plans = payload["plans"]
    if not plans:
        target = payload.get("trainer_query") or "강사"
        return f"{payload['date']} {target} 운동계획서를 찾지 못했어."
    plan = plans[0]
    return (
        f"{payload['date']} {plan['instructor_name']} 강사 운동계획서: "
        f"{_slot_label(plan['time_slot'])}, 완료 {plan['completed_count']}/{len(plan['exercises'])}."
    )


def _attendance_message(target_day: date, summary: dict[str, int]) -> str:
    return (
        f"{target_day.isoformat()} 출석 요약: 출석 {summary['present']}명, "
        f"지각 {summary['late']}명, 결석 {summary['absent']}명, 미체크 {summary['unknown']}명."
    )


def _slot_label(value: str) -> str:
    return {"morning": "오전반", "afternoon": "오후반", "evening": "저녁반"}.get(value, value or "시간대 미지정")


def _confirmation_fields(domain: str) -> list[str]:
    common = ["student", "academy_id", "requested_by", "before_value", "after_value"]
    if domain == "payment":
        return [*common, "amount", "payment_method", "paid_at"]
    if domain == "attendance":
        return [*common, "attendance_date", "attendance_status"]
    if domain == "record":
        return [*common, "record_type", "record_value", "measured_at"]
    return common


def _attendance_status(row: dict[str, Any]) -> str:
    return str(row.get("attendance_status") or row.get("status") or "").strip() or "unknown"


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


def _json_ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _date_arg(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _int_arg(value: Any, *, default: int, maximum: int) -> int:
    try:
        return max(1, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
