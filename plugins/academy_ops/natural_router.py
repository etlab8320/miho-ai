"""LLM-structured natural request router for academy operations."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import json
import logging
from typing import Any, Awaitable, Callable, ClassVar
from zoneinfo import ZoneInfo

from agent.temporal_semantics import build_temporal_reference, format_temporal_context
from .assignment_tool import _assignment_by_date_tool_handler
from .brand_logo_tool import (
    _academy_reset_brand_logo_tool_handler,
    _academy_set_brand_logo_tool_handler,
)
from .academy_calendar_tool import (
    _academy_schedule_range_tool_handler,
    _class_roster_range_tool_handler,
    _consultation_schedule_range_tool_handler,
)
from .academy_query_tools import (
    _attendance_day_tool_handler,
    _consultation_candidates_tool_handler,
    _plan_by_date_tool_handler,
    _student_summary_tool_handler,
)
from .attendance_calendar_tool import _student_attendance_calendar_image_tool_handler
from .commentary_config import (
    COMMENTARY_EXTRA_BODY,
    COMMENTARY_FALLBACK_TIMEOUT_SECONDS,
    COMMENTARY_PROVIDER,
    ROUTER_EXTRA_BODY,
    ROUTER_FALLBACK_MODELS,
    ROUTER_MODEL,
    ROUTER_MODEL_TIMEOUT_SECONDS,
)
from .consultation_notes_tool import _consultation_note_save_tool_handler
from .staff_schedule_tool import _staff_schedule_day_tool_handler
from .staff_attendance_tool import (
    _staff_attendance_day_tool_handler,
    _staff_attendance_range_tool_handler,
)
from .student_attendance_tool import _student_attendance_range_tool_handler
from .student_card_tool import _student_card_image_tool_handler
from .student_context_tool import _student_context_tool_handler
from .monthly_test_records_tool import _monthly_test_records_tool_handler
from .student_records_tool import _student_record_lookup_tool_handler
from .response_commentary import append_summary_comment_or_fallback
from .response_focus import focused_response
from .response_synthesis import compact_payload, synthesize_or_fallback
from .route_overrides import forced_tool_for_output_request, should_render_attendance_day_image
from .routing_decision import reject_execute_reason
from .thread_context import (
    INHERITABLE_ENTITY_ARGS,
    MONTHLY_TEST_CONTEXT_TOOLS,
    _is_blank,
    get_thread_context,
    pop_pending_request,
    remember_pending_request,
    remember_thread_context,
)


logger = logging.getLogger(__name__)
Resolver = Callable[[list[dict[str, str]]], Awaitable[Any]]
ToolHandler = Callable[..., str]

ROUTER_TASK = "academy_request_router"
ROUTER_TIMEOUT_SECONDS = 18
ROUTER_MAX_ATTEMPTS = 1
TOOL_TIMEOUT_SECONDS = 70
MIN_CONFIDENCE = 0.55
TIMEOUT_RESPONSE = "지금 학원 서버 응답이 불안정해서 요청을 처리하지 못했어. 잠시 후 다시 한 번 보내줘."


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "academy_schedule_range": _academy_schedule_range_tool_handler,
    "academy_class_roster_range": _class_roster_range_tool_handler,
    "academy_consultation_schedule_range": _consultation_schedule_range_tool_handler,
    "academy_student_attendance_range": _student_attendance_range_tool_handler,
    "academy_student_attendance_calendar_image": _student_attendance_calendar_image_tool_handler,
    "academy_attendance_day": _attendance_day_tool_handler,
    "academy_staff_attendance_day": _staff_attendance_day_tool_handler,
    "academy_staff_attendance_range": _staff_attendance_range_tool_handler,
    "academy_staff_schedule_day": _staff_schedule_day_tool_handler,
    "academy_plan_by_date": _plan_by_date_tool_handler,
    "academy_assignment_by_date": _assignment_by_date_tool_handler,
    "academy_consultation_candidates": _consultation_candidates_tool_handler,
    "academy_consultation_note_save": _consultation_note_save_tool_handler,
    "academy_student_summary": _student_summary_tool_handler,
    "academy_student_card_image": _student_card_image_tool_handler,
    "academy_student_context": _student_context_tool_handler,
    "academy_student_record_lookup": _student_record_lookup_tool_handler,
    "academy_monthly_test_records": _monthly_test_records_tool_handler,
    "academy_set_brand_logo": _academy_set_brand_logo_tool_handler,
    "academy_reset_brand_logo": _academy_reset_brand_logo_tool_handler,
}

TOOL_CONTRACTS: dict[str, dict[str, Any]] = {
    "academy_schedule_range": {
        "purpose": "학원 행사/이벤트(academy_events) 조회 — 맥스컵, 월말 테스트, 휴일, 업무일정. 학생 출석/등원과는 무관",
        "args": ["start_date", "end_date"],
    },
    "academy_class_roster_range": {
        "purpose": "오늘 출석할/등원할 학생, 수업 일정별 배정 학생 명단(이름/학교/학년/출결상태) 조회. class_schedules 기반",
        "args": ["start_date", "end_date", "with_roster"],
        "aliases": ["오늘 출석할 학생", "오늘 등원할 학생", "오늘 수업", "수업 명단", "수업별 학생"],
    },
    "academy_consultation_schedule_range": {
        "purpose": "신규 상담, 상담 일정, 체험수업, 무료체험, trial lesson 일정 조회",
        "args": ["start_date", "end_date", "new_registration_only", "trial_only"],
        "aliases": ["체험수업", "무료체험", "체험상담", "trial", "trial lesson"],
    },
    "academy_student_attendance_range": {
        "purpose": "특정 학생의 기간별 출석, 지각, 결석, 미체크 조회",
        "args": ["student_query", "start_date", "end_date", "today"],
    },
    "academy_student_attendance_calendar_image": {
        "purpose": "특정 학생의 출석을 달력 PNG 이미지로 생성. 날짜별 긴 출석 목록, 달력, 이미지 요청에 사용",
        "args": ["student_query", "start_date", "end_date", "today"],
    },
    "academy_attendance_day": {"purpose": "특정 날짜의 학생 전체 출석 현황/명단 조회와 PNG 이미지 생성", "args": ["date", "image"]},
    "academy_staff_attendance_day": {
        "purpose": "이미 출근한 강사, 출근 기록, 어제/과거 출근자 조회",
        "args": ["date"],
    },
    "academy_staff_attendance_range": {
        "purpose": "특정 강사의 기간별 출근 기록, 월간 출근 횟수, 지난주/이번달 출근일 조회",
        "args": ["staff_query", "start_date", "end_date"],
    },
    "academy_staff_schedule_day": {
        "purpose": "출근 예정 강사, 앞으로 출근해야 할 강사, 배정된 강사 조회",
        "args": ["date", "time_slot", "include_owner"],
    },
    "academy_plan_by_date": {
        "purpose": "날짜별 또는 강사별 운동계획서, 운동 목록, 완료 여부 조회",
        "args": ["date", "trainer_query", "time_slot"],
    },
    "academy_assignment_by_date": {"purpose": "날짜별 반배치와 담당 강사 조회", "args": ["date", "time_slot"]},
    "academy_consultation_candidates": {
        "purpose": "재원생 중 상담이 필요한 학생 후보 추천과 PNG 이미지 생성. 최근 2주 출결과 최근 5개 실기기록 추세를 서버 API로 조회",
        "args": ["today", "period_days", "limit"],
    },
    "academy_consultation_note_save": {
        "purpose": "특정 학생 상담 기록 저장. 사용자가 상담 내용, 팔로업, 등원 사유 등을 기록해달라고 할 때 사용",
        "args": ["student_query", "note", "consulted_at"],
    },
    "academy_student_summary": {"purpose": "학생 요약 텍스트 조회. 카드/이미지/파일 전달 요청에는 쓰지 않음", "args": ["student_query", "today", "period_days"]},
    "academy_student_card_image": {"purpose": "학생관리카드, 학생 카드, 카드 이미지를 PNG로 생성", "args": ["student_query", "today", "period_days"]},
    "academy_student_context": {
        "purpose": (
            "특정 학생의 수업 요일, 시간대, 최근 출석 요일, PACA/Peak ID 매핑, "
            "최근 기록 컨텍스트 조회. 학생 후속 질문이나 모호한 읽기 질문에 우선 사용"
        ),
        "args": ["student_query", "today", "period_days"],
    },
    "academy_student_record_lookup": {
        "purpose": "특정 학생의 Peak 실기, 측정, 종목별 기록 조회. 출석 기록, 강사 출근, 운동계획서가 아니라 학생 수행 기록일 때 사용",
        "args": ["student_query", "event_query", "date", "today", "period_days"],
    },
    "academy_monthly_test_records": {"purpose": "월별 또는 정기 실기 평가 참가자 기준 종목 평균, 순위, 학교 제외 집계 조회. 일반 최신 학생 기록이 아니라 평가 참가자 집계를 원할 때 사용", "args": ["event_query", "test_id", "test_month", "exclude_schools", "today"]},
    "academy_set_brand_logo": {
        "purpose": "사용자가 이미지를 첨부하고 학원 로고를 그 이미지로 바꿔/교체/설정해달라고 할 때 사용. 첨부 이미지를 학원 로고로 저장해 리포트/카드 스탬프에 적용. 인자 없음",
        "args": [],
        "aliases": ["로고 바꿔", "로고 교체", "로고 이걸로", "로고 설정", "스탬프 바꿔"],
    },
    "academy_reset_brand_logo": {
        "purpose": "학원 로고를 기본/원래대로 되돌리거나 삭제해달라고 할 때 사용. 저장된 학원 로고를 지워 기본 스탬프로 복원. 인자 없음",
        "args": [],
        "aliases": ["로고 기본", "로고 원래대로", "로고 삭제", "로고 초기화"],
    },
}


@dataclass(frozen=True)
class AcademyNaturalRoute:
    action: str
    response_text: str = ""
    reason: str = ""

    ALLOW: ClassVar[str] = "allow"
    HANDLED: ClassVar[str] = "handled"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.action == other
        return super().__eq__(other)


async def default_resolver(messages: list[dict[str, str]]) -> Any:
    from agent.auxiliary_client import async_call_llm

    last_exc: Exception | None = None
    model_sequence = (ROUTER_MODEL, *ROUTER_FALLBACK_MODELS)
    for index, model in enumerate(model_sequence):
        try:
            return await async_call_llm(
                task=ROUTER_TASK,
                provider=COMMENTARY_PROVIDER,
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=260,
                timeout=(
                    ROUTER_MODEL_TIMEOUT_SECONDS
                    if index == 0
                    else COMMENTARY_FALLBACK_TIMEOUT_SECONDS
                ),
                extra_body=ROUTER_EXTRA_BODY,
            )
        except Exception as exc:
            last_exc = exc
            logger.info("academy request resolver model failed: %s (%s)", model, exc)
    raise last_exc or TimeoutError()


async def resolve_and_execute_academy_request(
    text: str,
    *,
    resolver: Resolver = default_resolver,
    handlers: dict[str, ToolHandler] | None = None,
    today: str | None = None,
    resolver_timeout: float = ROUTER_TIMEOUT_SECONDS,
    resolver_attempts: int = ROUTER_MAX_ATTEMPTS,
    tool_timeout: float = TOOL_TIMEOUT_SECONDS,
    synthesize: bool = True,
    context_key: str | None = None,
) -> AcademyNaturalRoute:
    clean = text.strip()
    if not clean or clean.startswith("/"):
        return AcademyNaturalRoute(AcademyNaturalRoute.ALLOW)
    pending_route = await _try_pending_request_retry(
        clean,
        handlers=handlers,
        tool_timeout=tool_timeout,
        synthesize=synthesize,
        context_key=context_key,
    )
    if pending_route is not None:
        return pending_route
    try:
        decision = await _resolve_decision_with_retry(
            clean,
            resolver,
            today=today,
            context_key=context_key,
            resolver_timeout=resolver_timeout,
            attempts=resolver_attempts,
        )
    except TimeoutError:
        # The intent-classifier (resolver LLM) was slow — that is NOT an academy
        # server failure, so don't reply "서버가 불안정해". The router is only a
        # fast shortcut; when it's unavailable, fall back to the proper path —
        # hand off to the body agent (Nous "the agent decides"), which has the
        # academy tools and recent thread history and can resolve it itself.
        logger.info("academy request resolver timed out -> ALLOW (body agent handles)")
        return AcademyNaturalRoute(AcademyNaturalRoute.ALLOW, reason="resolver_timeout")
    except Exception as exc:
        logger.info("academy request resolver failed: %s", exc)
        return AcademyNaturalRoute(AcademyNaturalRoute.ALLOW, reason="resolver_error")

    tool_name = str(decision.get("tool") or "").strip()
    active_handlers = handlers or TOOL_HANDLERS
    reject_reason = reject_execute_reason(
        decision,
        allowed_tools=active_handlers.keys(),
        min_confidence=MIN_CONFIDENCE,
    )
    if reject_reason:
        return AcademyNaturalRoute(AcademyNaturalRoute.ALLOW, reason=reject_reason)
    forced_tool = forced_tool_for_output_request(clean, tool_name)
    force_default_response = forced_tool == "academy_student_attendance_calendar_image"
    if forced_tool:
        tool_name = forced_tool
    handler = active_handlers.get(tool_name)
    if handler is None:
        return AcademyNaturalRoute(AcademyNaturalRoute.ALLOW, reason="unknown_tool")
    args = _resolved_args(
        tool_name,
        decision.get("args") if isinstance(decision.get("args"), dict) else {},
        context_key,
    )
    if should_render_attendance_day_image(clean, tool_name):
        args["image"] = True
    args = _with_reference_today(tool_name, args, today)
    # 원문을 kwargs로 함께 넘겨, LLM이 event 인자를 잘못 추출해도 도구가 원문에서 회수.
    handler_kwargs = {"source_text": clean} if tool_name in MONTHLY_TEST_CONTEXT_TOOLS else {}
    try:
        raw_result = await asyncio.wait_for(
            asyncio.to_thread(handler, args, **handler_kwargs),
            timeout=tool_timeout,
        )
    except TimeoutError:
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, _tool_timeout_message(), "tool_timeout")
    except Exception as exc:
        logger.info("academy tool execution failed: %s", exc)
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, "학원 데이터를 조회하다가 오류가 났어.")

    payload = _load_payload(raw_result)
    if _is_login_required_payload(payload):
        remember_pending_request(
            context_key,
            tool_name=tool_name,
            args=args,
            request_text=clean,
            reason="auth_required",
        )
    remember_thread_context(context_key, tool_name=tool_name, args=args, payload=payload)
    response_focus = "" if force_default_response else str(decision.get("response_focus") or "").strip()
    response = focused_response(payload, response_focus) or _payload_message(payload)
    if decision.get("skip_synthesis"):
        response = _payload_message(payload)
    elif response_focus == "summary" and synthesize and payload.get("ok") and not payload.get("media_tag"):
        response = await append_summary_comment_or_fallback(clean, compact_payload(payload), response)
    elif not response_focus and synthesize and payload.get("ok") and not payload.get("media_tag"):
        response = await synthesize_or_fallback(clean, payload, response)
    return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, response)


async def _resolve_decision_with_retry(
    text: str,
    resolver: Resolver,
    *,
    today: str | None,
    context_key: str | None,
    resolver_timeout: float,
    attempts: int = ROUTER_MAX_ATTEMPTS,
) -> dict[str, Any]:
    last_error: TimeoutError | None = None
    for attempt in range(max(1, attempts)):
        try:
            return await asyncio.wait_for(
                _resolve_decision(text, resolver, today=today, context_key=context_key),
                timeout=resolver_timeout,
            )
        except TimeoutError as exc:
            last_error = exc
            logger.info(
                "academy request resolver timed out: attempt %s/%s",
                attempt + 1,
                max(1, attempts),
            )
    raise last_error or TimeoutError()


async def _resolve_decision(
    text: str,
    resolver: Resolver,
    *,
    today: str | None,
    context_key: str | None,
) -> dict[str, Any]:
    reference_day = today or _today()
    response = await resolver(_resolver_messages(text, reference_day, get_thread_context(context_key)))
    payload = _load_payload(_response_content(response))
    return payload if isinstance(payload, dict) else {}


def _resolver_messages(
    text: str,
    today: str,
    thread_context: dict[str, Any] | None = None,
    temporal_context: str | None = None,
) -> list[dict[str, str]]:
    contracts = json.dumps(TOOL_CONTRACTS, ensure_ascii=False, sort_keys=True)
    context_text = json.dumps(thread_context or {}, ensure_ascii=False, sort_keys=True)
    temporal = temporal_context or format_temporal_context(build_temporal_reference())
    return [
        {
            "role": "system",
            "content": (
                "너는 Discord 학원업무 요청을 구조화하는 의미 기반 라우터야. "
                "사용자 문장을 직접 답하지 말고 JSON만 반환해. "
                "PACA/Peak 운영 도메인으로 확정되면 domain=academy_ops와 action=execute, "
                "그 외 요청이면 domain=non_academy와 action=allow로 반환해. "
                "키워드 하나가 아니라 전체 문맥, 사용자의 목적, 직전 학원업무 맥락을 함께 판단해. "
                "학원 도구를 실행하려면 ambiguous=false, intent, evidence를 반드시 채워. "
                "도메인이 조금이라도 불명확하면 action=allow, ambiguous=true로 둬. "
                "상대 날짜와 범위는 reference_date와 turn_time을 함께 보고 ISO 날짜로 넣어. "
                "도구 계약에 없는 인자는 만들지 말고, 모르는 값은 빈 문자열이나 false로 둬. "
                "출력 초점이 있으면 response_focus를 함께 반환해. "
                "가능한 response_focus는 summary, daily_attendance, unchecked_dates 중 하나야. "
                "기본 출석 조회는 response_focus=summary야. "
                "출석 요청에 이미지, 사진, PNG가 포함되고 특정 학생이 없으며 전체/명단/대상/해야할 학생 목적이면 "
                "academy_attendance_day에 image=true를 넣어. "
                "특정 학생 출석을 달력, 캘린더, 이미지, 긴 날짜별 화면으로 보려는 요청은 "
                "academy_student_attendance_calendar_image를 써. "
                "학생관리카드, 학생 카드, 카드 이미지 요청은 academy_student_summary가 아니라 academy_student_card_image를 써. "
                "직전 학원업무 맥락이 특정 학생 출석 조회이고 현재 후속 요청에 이미지, 사진, PNG, 달력, 캘린더가 있으면 "
                "academy_student_attendance_calendar_image를 써. "
                "사용자가 텍스트 날짜별, 일자별, 하루씩, 전체 날짜를 명시적으로 원할 때만 daily_attendance를 써. "
                "미체크 날짜만 원할 때는 unchecked_dates를 써. "
                "학생의 실기, 측정, 수행, 종목별 기록 조회는 academy_student_record_lookup을 써. "
                "월별 또는 정기 실기 평가의 남녀 평균, 참가자 집계, 순위, 학교 제외 계산은 academy_monthly_test_records를 써. "
                "event_query에는 순수 종목명만 넣어. 테스트명, 성별, 월, 평균/순위 같은 수식어는 빼고 "
                "측정 종목 그 자체만 넣고, 종목을 특정할 수 없으면 빈 문자열로 둬. "
                "학생 수행 기록 요청을 출석 기록, 강사 출근, 운동계획서 조회로 바꾸지 마. "
                "직전 학원업무 맥락이 있고 현재 요청이 후속 질문이면 그 맥락의 학생/기간을 이어받아. "
                "직전 맥락이 pending_request이고 현재 요청이 로그인 완료/재시도 후속이면 "
                "pending_request의 도구와 인자를 이어받아 실행해. "
                "현재 요청에 새 학생이 명시되지 않았다면 예시나 다른 대화에서 학생명을 추측하지 마. "
                "쓰기/반영/결제 완료 요청은 실행하지 말고 action=allow로 둬."
            ),
        },
        {
            "role": "user",
            "content": (
                f"reference_date: {today}\n"
                f"turn_time: {temporal}\n"
                f"직전 학원업무 맥락: {context_text}\n"
                f"도구 계약: {contracts}\n"
                '반환 형식: {"action":"execute|allow","domain":"academy_ops|non_academy|ambiguous",'
                '"intent":"사용자 목적","evidence":["학원업무로 판단한 근거"],"ambiguous":false,'
                '"tool":"도구명","args":{},"response_focus":"summary|daily_attendance|unchecked_dates",'
                '"confidence":0.0}\n'
                f"사용자 문장: {text}"
            ),
        },
    ]


def _resolved_args(tool_name: str, args: dict[str, Any], context_key: str | None) -> dict[str, Any]:
    """Fill args a follow-up question left implicit from the last academy turn.

    Generalised across all tools via TOOL_CONTRACTS: any inheritable entity arg
    (student/staff/event/trainer) the current tool declares but the user omitted
    is carried over from the prior context. Previously only 7 whitelisted tools
    did this, so follow-ups after e.g. a record lookup lost their subject.
    """
    context = get_thread_context(context_key)
    if not context:
        return args
    contract_args = TOOL_CONTRACTS.get(tool_name, {}).get("args", [])
    resolved = dict(args)
    # Carry the subject (학생/강사/종목/트레이너) into follow-ups that omit it.
    for name in INHERITABLE_ENTITY_ARGS:
        if name in contract_args and _is_blank(resolved.get(name)) and not _is_blank(context.get(name)):
            resolved[name] = context[name]
    # Carry the date range forward only for subject-scoped queries (a student's
    # or staff's range). Subject-less tools like academy_schedule_range must not
    # inherit a prior student's window, so gate on having an entity arg.
    has_entity_arg = any(name in contract_args for name in INHERITABLE_ENTITY_ARGS)
    if has_entity_arg and "start_date" in contract_args:
        if _is_blank(resolved.get("start_date")) and context.get("start_date"):
            resolved["start_date"] = context["start_date"]
        if _is_blank(resolved.get("end_date")) and context.get("end_date"):
            resolved["end_date"] = context["end_date"]
    # Monthly test: keep looking at the same test when not re-specified.
    if "test_id" in contract_args and "test_month" in contract_args:
        if resolved.get("test_id") is None and _is_blank(resolved.get("test_month")):
            if context.get("test_id") is not None:
                resolved["test_id"] = context["test_id"]
            elif context.get("test_month"):
                resolved["test_month"] = context["test_month"]
    return resolved


def _with_reference_today(tool_name: str, args: dict[str, Any], today: str | None) -> dict[str, Any]:
    if "today" not in TOOL_CONTRACTS.get(tool_name, {}).get("args", []):
        return args
    if str(args.get("today") or "").strip():
        return args
    resolved = dict(args)
    resolved["today"] = today or _today()
    return resolved


async def _try_pending_request_retry(
    text: str,
    *,
    handlers: dict[str, ToolHandler] | None,
    tool_timeout: float,
    synthesize: bool,
    context_key: str | None,
) -> AcademyNaturalRoute | None:
    pending = get_thread_context(context_key)
    if pending.get("kind") != "pending_request":
        return None
    tool_name = str(pending.get("tool") or "")
    args = pending.get("args") if isinstance(pending.get("args"), dict) else {}
    handler = (handlers or TOOL_HANDLERS).get(tool_name)
    if handler is None:
        pop_pending_request(context_key)
        return None
    try:
        raw_result = await asyncio.wait_for(asyncio.to_thread(handler, args), timeout=tool_timeout)
    except TimeoutError:
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, _tool_timeout_message(), "pending_tool_timeout")
    except Exception as exc:
        logger.info("academy pending request retry failed: %s", exc)
        return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, "학원 데이터를 다시 조회하다가 오류가 났어.")
    pop_pending_request(context_key)
    payload = _load_payload(raw_result)
    if _is_login_required_payload(payload):
        remember_pending_request(context_key, tool_name=tool_name, args=args, request_text=text, reason="auth_required")
    remember_thread_context(context_key, tool_name=tool_name, args=args, payload=payload)
    response = _payload_message(payload)
    if synthesize and payload.get("ok") and not payload.get("media_tag"):
        response = await synthesize_or_fallback(text, payload, response)
    return AcademyNaturalRoute(AcademyNaturalRoute.HANDLED, response, "pending_request_retry")


def _response_content(response: Any) -> str:
    try:
        return str(response.choices[0].message.content or "")
    except (AttributeError, IndexError, TypeError):
        return str(response or "")


def _load_payload(text: str) -> dict[str, Any]:
    clean = text.strip()
    if clean.startswith("```"):
        lines = clean.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean = "\n".join(lines).strip()
    try:
        payload = json.loads(clean)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_message(payload: dict[str, Any]) -> str:
    return str(payload.get("message") or "조회 결과를 정리하지 못했어.")


def _is_login_required_payload(payload: dict[str, Any]) -> bool:
    if payload.get("ok") is not False:
        return False
    message = str(payload.get("message") or "")
    return "/academy login" in message or "학원 계정 연결" in message


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()


def _tool_timeout_message() -> str:
    return "PACA/Peak API 조회가 제한시간을 넘겨서 중단했어. 잠시 뒤 다시 시도해줘."
