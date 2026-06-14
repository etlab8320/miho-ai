"""Academy operations plugin for PACA/Peak Discord workflows."""
from __future__ import annotations

import json
from typing import Any

from .auth_flow import refresh_remote_pending_logins
from .auth_store import get_binding
from .catalog import operations_payload
from .brand_logo_tool import register_brand_logo_tools
from .commentary_config import plan_commentary_aux_defaults
from .consultation_notes_tool import register_consultation_note_tool
from .hakjong_report_tool import register_hakjong_report_tool
from .practical_reco_tool import register_practical_reco_tool
from .hakjong_qualitative_tool import register_hakjong_qualitative_tool
from .gateway_dispatch import (
    _academy_command,
    _academy_pre_gateway_dispatch,
    _capture_gateway_context,
    _inject_prior_context,
    _persist_handled_turn,
)
from .academy_query_tools import (
    _attendance_day_tool_handler,
    _capability_status_tool_handler,
    _consultation_candidates_tool_handler,
    _plan_by_date_tool_handler,
    _student_summary_tool_handler,
    _write_action_draft_tool_handler,
)
from .academy_calendar_tool import (
    _academy_schedule_range_tool_handler,
    _class_roster_range_tool_handler,
    _consultation_schedule_range_tool_handler,
)
from .api_query_tool import register_api_query_tool
from .expense_tools import register_expense_tools
from .assignment_tool import _assignment_by_date_tool_handler
from .attendance_calendar_tool import _student_attendance_calendar_image_tool_handler
from .staff_attendance_tool import register_staff_attendance_tools
from .staff_schedule_tool import _staff_schedule_day_tool_handler
from .student_attendance_tool import register_student_attendance_tool
from .student_card_tool import _student_card_image_tool_handler
from .student_context_tool import _student_context_tool_handler
from .monthly_test_records_tool import register_monthly_test_records_tool
from .student_record_cohort_tool import register_student_record_cohort_tool
from .student_record_chart_tool import register_student_record_chart_tool
from .student_records_tool import register_student_records_tool
from .report_render_tool import register_report_image_tool
from .render_image_tool import register_render_image_tool


def _catalog_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    """Return the academy operation catalog."""
    return json.dumps(operations_payload(), ensure_ascii=False)


def register(ctx: Any) -> None:
    ctx.register_command(
        "academy",
        _academy_command,
        description="PACA/Peak 로그인 연결, 기능 카탈로그, 실행 전 미리보기",
        args_hint="[요청]",
    )
    ctx.register_hook("pre_gateway_dispatch", _academy_pre_gateway_dispatch)
    ctx.register_auxiliary_task(
        key="academy_plan_commentary",
        display_name="Academy plan commentary",
        description="Short Korean commentary for Peak workout-plan facts",
        defaults=plan_commentary_aux_defaults(),
    )
    # academy_operations_catalog / academy_capability_status: meta tools the body
    # never called (0 invocations in logs) — they only listed/checked capabilities,
    # which the agent does by just trying the real tools. Removed to cut tool-list
    # noise (better tool-selection accuracy). The /academy command still shows the
    # catalog via format_catalog(); these were redundant as model-facing tools.
    ctx.register_tool(
        name="academy_student_card_image",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_query": {
                    "type": "string",
                    "description": "학생 이름, 학교, 또는 PACA 검색어.",
                },
                "period_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 60,
                    "default": 14,
                    "description": "출결을 집계할 최근 일수. 기본값은 최근 2주.",
                },
                "today": {
                    "type": "string",
                    "description": "기준 날짜. YYYY-MM-DD 형식.",
                },
            },
            "required": ["student_query"],
            "additionalProperties": False,
        },
        handler=_student_card_image_tool_handler,
        description=(
            "Create a safe PACA/Peak student-card PNG from live academy data. "
            "Use for student card, student management card, or student-card image requests. "
            "Excludes sensitive finance/contact details and returns a MEDIA:<path> tag for Discord image delivery."
        ),
    )
    ctx.register_tool(
        name="academy_student_summary",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_query": {"type": "string", "description": "학생 이름, 학교, 또는 PACA 검색어."},
                "period_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 60,
                    "default": 14,
                    "description": "출결을 집계할 최근 일수. 기본값은 최근 2주.",
                },
                "today": {"type": "string", "description": "기준 날짜. YYYY-MM-DD 형식."},
            },
            "required": ["student_query"],
            "additionalProperties": False,
        },
        handler=_student_summary_tool_handler,
        description=(
            "Return safe structured PACA/Peak student overview data without creating an image. "
            "Use for natural-language student overview or 상담 포인트 requests. "
            "Do not use for student-card, image, or file-delivery requests; use academy_student_card_image. "
            "The assistant should write persona commentary from the returned facts, not from a fixed template."
        ),
    )
    ctx.register_tool(
        name="academy_student_context",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_query": {"type": "string", "description": "학생 이름, 부분 이름, 또는 PACA 학생 ID."},
                "period_days": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 60,
                    "default": 14,
                    "description": "최근 출석 컨텍스트를 조회할 일수. 기본값은 최근 2주.",
                },
                "today": {"type": "string", "description": "기준 날짜. YYYY-MM-DD 형식."},
            },
            "required": ["student_query"],
            "additionalProperties": False,
        },
        handler=_student_context_tool_handler,
        description=(
            "Return fast read-only PACA/Peak context for one student: class days, time slots, "
            "recent attendance days, PACA/Peak id mapping, and recent record summaries. "
            "Use for student follow-up questions such as which days the student attends. "
            "Never guess if the API says multiple students matched."
        ),
    )
    register_student_attendance_tool(ctx)
    register_student_record_cohort_tool(ctx)
    register_student_record_chart_tool(ctx)
    register_student_records_tool(ctx)
    register_monthly_test_records_tool(ctx)
    register_report_image_tool(ctx)
    register_render_image_tool(ctx)
    register_consultation_note_tool(ctx)
    register_brand_logo_tools(ctx)
    register_hakjong_report_tool(ctx)
    register_practical_reco_tool(ctx)
    register_hakjong_qualitative_tool(ctx)
    register_api_query_tool(ctx)
    register_expense_tools(ctx)
    ctx.register_tool(
        name="academy_student_attendance_calendar_image",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_query": {"type": "string", "description": "학생 이름, 학교, 또는 PACA 검색어."},
                "start_date": {"type": "string", "description": "조회 시작일. YYYY-MM-DD 형식."},
                "end_date": {"type": "string", "description": "조회 종료일. YYYY-MM-DD 형식."},
                "today": {"type": "string", "description": "기준일. 보통 라우터 기준일이며 YYYY-MM-DD 형식."},
            },
            "required": ["student_query", "start_date", "end_date"],
            "additionalProperties": False,
        },
        handler=_student_attendance_calendar_image_tool_handler,
        description=(
            "Create a safe PACA attendance calendar PNG for one student over an explicit date range. "
            "Use for requests asking to see student attendance as a calendar, image, card, or long date-by-date view. "
            "No-class days are left unmarked. Returns a MEDIA:<path> tag for Discord image delivery."
        ),
    )
    ctx.register_tool(
        name="academy_attendance_day",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "조회 날짜. YYYY-MM-DD 형식."},
                "image": {"type": "boolean", "default": False, "description": "하루 전체 출석 명단 PNG 필요 여부."},
            },
            "required": ["date"],
            "additionalProperties": False,
        },
        handler=_attendance_day_tool_handler,
        description=(
            "ALREADY-RECORDED attendance (출결 기록) for one explicit date — 출석/지각/결석/미체크 현황, grouped by slot, as summary or PNG. "
            "Use ONLY for past/today actual attendance. A FUTURE date has no attendance recorded yet (everyone shows 미체크 0), "
            "so for '출석해야 할 / 나와야 할 / 예정' 학생 명단 (future or planned roster) use academy_class_roster_range instead — NOT this tool. "
            "Do not call with empty arguments; resolve natural-language dates to YYYY-MM-DD first."
        ),
    )
    register_staff_attendance_tools(ctx)
    ctx.register_tool(
        name="academy_staff_schedule_day",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "조회 날짜. LLM이 해석한 YYYY-MM-DD 형식.",
                },
                "time_slot": {
                    "type": "string",
                    "description": "morning, afternoon, evening 중 하나.",
                },
                "include_owner": {
                    "type": "boolean",
                    "default": False,
                    "description": "원장까지 포함할지 여부. 강사 질문은 기본 False, 사용자가 원장 포함을 명시하면 True.",
                },
            },
            "required": ["date"],
            "additionalProperties": False,
        },
        handler=_staff_schedule_day_tool_handler,
        description=(
            "Return one day's Peak work schedule for INSTRUCTORS (who is scheduled to work). "
            "Use for future/scheduled/should-work or staff-schedule questions about instructors. "
            "For which students are assigned to which class, use academy_assignment_by_date instead. "
            "Do not call with empty arguments; resolve natural-language dates to YYYY-MM-DD first."
        ),
    )
    ctx.register_tool(
        name="academy_plan_by_date",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "조회 날짜. LLM이 해석한 YYYY-MM-DD 형식."},
                "trainer_query": {"type": "string", "description": "LLM이 해석한 필터링할 강사 이름."},
                "time_slot": {"type": "string", "description": "morning, afternoon, evening 중 하나."},
            },
            "required": ["date"],
            "additionalProperties": False,
        },
        handler=_plan_by_date_tool_handler,
        description=(
            "Return Peak daily workout plans from live Peak plan records. "
            "Use for teacher/trainer workout-plan questions. "
            "Do not call with empty arguments; resolve natural-language dates to YYYY-MM-DD first."
        ),
    )
    ctx.register_tool(
        name="academy_assignment_by_date",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "조회 날짜. YYYY-MM-DD 형식."},
                "time_slot": {"type": "string", "description": "morning, afternoon, evening 중 하나."},
            },
            "required": ["date"],
            "additionalProperties": False,
        },
        handler=_assignment_by_date_tool_handler,
        description=(
            "Return safe Peak class assignments for an explicit date and optional time slot. "
            "The assistant must resolve natural-language dates into date before calling this tool. "
            "Do not call with empty arguments. Excludes phone numbers and private notes."
        ),
    )
    ctx.register_tool(
        name="academy_consultation_candidates",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "today": {"type": "string", "description": "기준 날짜. YYYY-MM-DD 형식."},
                "period_days": {"type": "integer", "minimum": 1, "maximum": 30, "default": 14},
                "limit": {"type": "integer", "minimum": 1, "maximum": 30, "default": 10},
            },
            "additionalProperties": False,
        },
        handler=_consultation_candidates_tool_handler,
        description=(
            "Return read-only consultation candidates from recent Peak attendance signals and attach a PNG image when candidates exist. "
            "Does not use payment data or private memos."
        ),
    )
    ctx.register_tool(
        name="academy_schedule_range",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "조회 시작일. YYYY-MM-DD 형식."},
                "end_date": {"type": "string", "description": "조회 종료일. YYYY-MM-DD 형식."},
            },
            "required": ["start_date", "end_date"],
            "additionalProperties": False,
        },
        handler=_academy_schedule_range_tool_handler,
        description=(
            "Return PACA academy EVENTS/계획 (학원 행사·이벤트, academy_events table) for an explicit date range — "
            "things like 맥스컵, 월말 테스트, holidays, 업무일정. "
            "This is NOT about which students attend class. "
            "For who attends/등원할/출석할 학생 or class rosters, use academy_class_roster_range instead. "
            "The assistant must resolve natural-language periods such as this week, next week, "
            "or a month into start_date/end_date before calling this tool. "
            "Do not call with empty arguments."
        ),
    )
    ctx.register_tool(
        name="academy_class_roster_range",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "조회 시작일. YYYY-MM-DD 형식."},
                "end_date": {"type": "string", "description": "조회 종료일. YYYY-MM-DD 형식."},
                "with_roster": {
                    "type": "boolean",
                    "default": True,
                    "description": "각 수업의 배정 학생 명단까지 펼칠지 여부. False면 수업별 인원수만.",
                },
            },
            "required": ["start_date", "end_date"],
            "additionalProperties": False,
        },
        handler=_class_roster_range_tool_handler,
        description=(
            "특정 날짜(오늘뿐 아니라 이번주/다음주 등 미래 날짜 포함)에 출석·등원 '예정'인, 수업에 배정된 학생 명단 — class_schedules 기반 (아직 출결 체크 전의 '예정자'). "
            "Return PACA class schedules (수업 일정) for a date range and, for each class, the assigned student "
            "roster (이름/학교/학년) from live PACA data. "
            "'출석해야 할 / 나와야 할 / 등원 예정' 학생 명단은 날짜와 무관하게(미래 날짜도) 이 도구를 써라. 과거·오늘의 실제 '출결 기록'은 academy_attendance_day. "
            "Use for '오늘/이번주 금요일 출석할 학생', '나와야 할 학생', '수업별 학생 명단'. "
            "명단을 이미지로 달라고 하면, 이 도구로 데이터를 얻은 뒤 academy_render_image로 HTML을 만들어 PNG로 줘라. "
            "학원 행사/이벤트(academy_events)는 academy_schedule_range로 따로 조회. "
            "The assistant must resolve natural-language periods into start_date/end_date first. "
            "Do not call with empty arguments."
        ),
    )
    ctx.register_tool(
        name="academy_consultation_schedule_range",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "조회 시작일. YYYY-MM-DD 형식."},
                "end_date": {"type": "string", "description": "조회 종료일. YYYY-MM-DD 형식."},
                "new_registration_only": {
                    "type": "boolean",
                    "default": True,
                    "description": "신규 등록 상담만 볼지 여부.",
                },
                "trial_only": {
                    "type": "boolean",
                    "default": False,
                    "description": "체험수업/무료체험 일정만 볼지 여부.",
                },
            },
            "required": ["start_date", "end_date"],
            "additionalProperties": False,
        },
        handler=_consultation_schedule_range_tool_handler,
        description=(
            "Return safe PACA consultation schedules for an explicit date range. "
            "Excludes phone numbers, checklists, admin notes, and long inquiry text. "
            "The assistant must resolve natural-language periods into start_date/end_date first. "
            "Do not call with empty arguments."
        ),
    )
    ctx.register_tool(
        name="academy_prepare_write_action",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "request": {"type": "string", "description": "사용자가 반영하려는 학원 업무 원문."},
                "operation_key": {"type": "string", "description": "LLM이 선택한 쓰기 작업 catalog operation key."},
            },
            "required": ["operation_key"],
            "additionalProperties": False,
        },
        handler=_write_action_draft_tool_handler,
        description=(
            "Draft a guarded PACA/Peak write action without mutating data. "
            "Use for payment, attendance, or record update requests before showing confirmation UI."
        ),
    )
