"""Academy operations plugin for PACA/Peak Discord workflows."""

from __future__ import annotations

import json
from typing import Any

from .auth_flow import LINK_TTL_SECONDS, create_login_link, resolve_auth_base_url
from .auth_store import delete_binding, get_binding
from .catalog import operations_payload
from .context import (
    CHANNEL_ID,
    DISCORD_USER_ID,
    GUILD_ID,
    capture_gateway_context,
    set_gateway_context,
)
from .commentary_config import plan_commentary_aux_defaults
from .formatting import (
    format_binding_status,
    format_catalog,
    format_login_link,
)
from .fast_model_routing import route_bound_academy_session_to_fast_model
from .natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from .thread_context import academy_context_key
from .academy_query_tools import (
    _attendance_day_tool_handler,
    _capability_status_tool_handler,
    _consultation_candidates_tool_handler,
    _plan_by_date_tool_handler,
    _staff_attendance_day_tool_handler,
    _student_summary_tool_handler,
    _write_action_draft_tool_handler,
)
from .academy_calendar_tool import (
    _academy_schedule_range_tool_handler,
    _consultation_schedule_range_tool_handler,
)
from .assignment_tool import _assignment_by_date_tool_handler
from .attendance_calendar_tool import _student_attendance_calendar_image_tool_handler
from .staff_schedule_tool import _staff_schedule_day_tool_handler
from .student_attendance_tool import register_student_attendance_tool
from .student_card_tool import _student_card_image_tool_handler


def _catalog_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    """Return the academy operation catalog.

    Plugin tools may receive execution metadata such as ``task_id`` as keyword
    arguments from the tool dispatcher, so accept and ignore extra kwargs.
    """
    return json.dumps(operations_payload(), ensure_ascii=False)


def _academy_command(raw_args: str = "") -> str:
    text = raw_args.strip()
    if not text:
        return format_catalog()
    subcommand, _, remainder = text.partition(" ")
    normalized = subcommand.lower().strip()
    if normalized == "quick":
        return "빠른 문장 가로채기는 꺼져 있어. 일반 문장으로 요청하면 미호가 판단해서 필요한 도구를 호출할게."
    if normalized == "login":
        return _login_command()
    if normalized == "status":
        return _status_command()
    if normalized == "logout":
        return _logout_command()
    if normalized == "link":
        return _login_command()
    return format_catalog()


def _login_command() -> str:
    discord_user_id = DISCORD_USER_ID.get()
    if not discord_user_id:
        return "디스코드 사용자 정보를 확인하지 못했어. 디스코드에서 `/academy login`으로 다시 실행해줘."
    link = create_login_link(
        discord_user_id=discord_user_id,
        guild_id=GUILD_ID.get(),
        channel_id=CHANNEL_ID.get(),
    )
    base_url = resolve_auth_base_url()
    return format_login_link(
        link.url,
        LINK_TTL_SECONDS // 60,
        is_local=base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost"),
    )


def _status_command() -> str:
    discord_user_id = DISCORD_USER_ID.get()
    if not discord_user_id:
        return "디스코드 사용자 정보를 확인하지 못했어."
    binding = get_binding(discord_user_id)
    if binding is None:
        return "아직 학원 계정이 연결되지 않았어. `/academy login`으로 먼저 연결해줘."
    return format_binding_status(binding.name, binding.academy_name, binding.role)


def _logout_command() -> str:
    discord_user_id = DISCORD_USER_ID.get()
    if not discord_user_id:
        return "디스코드 사용자 정보를 확인하지 못했어."
    if delete_binding(discord_user_id):
        return "학원 계정 연결을 해제했어."
    return "연결된 학원 계정이 없었어."


def _capture_gateway_context(event: Any = None, **kwargs: Any) -> dict[str, str]:
    capture_gateway_context(event)
    gateway = kwargs.get("gateway")
    set_gateway_context(gateway)
    discord_user_id = DISCORD_USER_ID.get()
    route_bound_academy_session_to_fast_model(
        gateway=gateway,
        event=event,
        has_binding=bool(discord_user_id and get_binding(discord_user_id)),
    )
    return {"action": "allow"}


async def _academy_pre_gateway_dispatch(event: Any = None, **kwargs: Any) -> dict[str, str]:
    _capture_gateway_context(event, **kwargs)
    source = getattr(event, "source", None)
    platform = str(getattr(getattr(source, "platform", None), "value", "") or "")
    discord_user_id = DISCORD_USER_ID.get()
    if platform != "discord" or not discord_user_id or get_binding(discord_user_id) is None:
        return {"action": "allow"}
    route = await resolve_and_execute_academy_request(
        str(getattr(event, "text", "") or ""),
        context_key=academy_context_key(event),
    )
    if route == AcademyNaturalRoute.HANDLED:
        return {"action": "respond", "text": route.response_text}
    return {"action": "allow"}


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
    ctx.register_tool(
        name="academy_operations_catalog",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=_catalog_tool_handler,
        description="Return the PACA/Peak Discord operation catalog and safety policy.",
    )
    ctx.register_tool(
        name="academy_capability_status",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "operation_key": {
                    "type": "string",
                    "description": "LLM이 선택한 catalog operation key.",
                },
            },
            "required": ["operation_key"],
            "additionalProperties": False,
        },
        handler=_capability_status_tool_handler,
        description=(
            "Return implementation status for a PACA/Peak catalog operation key selected by the LLM."
        ),
    )
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
            "Use for natural-language requests asking for a student card or student overview. "
            "Excludes phone numbers, tuition, discounts, payment details, and internal memos. "
            "Returns a MEDIA:<path> tag for Discord image delivery."
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
            "Use for natural-language student overview, 상담 포인트, or student-card planning requests. "
            "The assistant should write persona commentary from the returned facts, not from a fixed template."
        ),
    )
    register_student_attendance_tool(ctx)
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
            },
            "required": ["date"],
            "additionalProperties": False,
        },
        handler=_attendance_day_tool_handler,
        description=(
            "Return a safe Peak attendance summary for one explicit date, grouped by slot. "
            "Do not call with empty arguments; resolve natural-language dates to YYYY-MM-DD first."
        ),
    )
    ctx.register_tool(
        name="academy_staff_attendance_day",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "조회 날짜. LLM이 해석한 YYYY-MM-DD 형식.",
                },
            },
            "required": ["date"],
            "additionalProperties": False,
        },
        handler=_staff_attendance_day_tool_handler,
        description=(
            "Return PACA instructor attendance for one day from live instructor attendance records. "
            "Use for teacher/staff/instructor work-attendance questions. "
            "Do not call with empty arguments; resolve natural-language dates to YYYY-MM-DD first."
        ),
    )
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
            "Return Peak instructor schedule for one day from live assignment records. "
            "Use for future, scheduled, should-work, assignment, or staff schedule questions. "
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
            "Return read-only consultation candidates from recent Peak attendance signals. "
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
            "Return safe PACA business/academy calendar events for an explicit date range. "
            "The assistant must resolve natural-language periods such as this week, next week, "
            "or a month into start_date/end_date before calling this tool. "
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
