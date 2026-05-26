"""Academy operations plugin for PACA/Peak Discord workflows."""

from __future__ import annotations

import json
from typing import Any

from .auth_flow import LINK_TTL_SECONDS, create_login_link, resolve_auth_base_url
from .auth_store import delete_binding, get_binding
from .catalog import operations_payload
from .context import CHANNEL_ID, DISCORD_USER_ID, GUILD_ID, capture_gateway_context
from .date_parser import parse_academy_date
from .formatting import (
    format_binding_status,
    format_catalog,
    format_intent_preview,
    format_login_link,
)
from .intent import draft_intent
from .academy_query_tools import (
    _attendance_day_tool_handler,
    _capability_status_tool_handler,
    _consultation_candidates_tool_handler,
    _staff_attendance_day_tool_handler,
    _student_summary_tool_handler,
    _write_action_draft_tool_handler,
)
from .quick_router import quick_command_for
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
        return _quick_command(remainder)
    if normalized == "login":
        return _login_command()
    if normalized == "status":
        return _status_command()
    if normalized == "logout":
        return _logout_command()
    if normalized == "link":
        return _login_command()
    return format_intent_preview(draft_intent(text))


def _quick_command(raw_args: str) -> str:
    operation_key, _, request = raw_args.strip().partition(" ")
    if operation_key == "staff.attendance_day":
        target_day = parse_academy_date(request)
        raw = _staff_attendance_day_tool_handler({"date": target_day.isoformat()})
        payload = json.loads(raw)
        if not payload.get("ok"):
            return str(payload.get("message") or "강사 출근 목록을 조회하지 못했어.")
        names = [row["name"] for row in payload.get("instructors", []) if row.get("name")]
        if not names:
            return f"{payload['date']} 출근 기록이 있는 강사는 없어."
        return f"{payload['date']} 출근 강사: {', '.join(names)}."
    return "바로 처리할 수 있는 학원 업무를 찾지 못했어."


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
    discord_user_id = DISCORD_USER_ID.get()
    command = quick_command_for(str(getattr(event, "text", "") or "")) if get_binding(discord_user_id) else ""
    if command:
        return {"action": "rewrite", "text": command}
    return {"action": "allow"}


def register(ctx: Any) -> None:
    ctx.register_command(
        "academy",
        _academy_command,
        description="PACA/Peak 로그인 연결, 기능 카탈로그, 실행 전 미리보기",
        args_hint="[요청]",
    )
    ctx.register_hook("pre_gateway_dispatch", _capture_gateway_context)
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
                "request": {
                    "type": "string",
                    "description": "사용자의 PACA/Peak 학원 업무 요청 원문.",
                },
            },
            "required": ["request"],
            "additionalProperties": False,
        },
        handler=_capability_status_tool_handler,
        description=(
            "Classify a natural-language PACA/Peak academy request against connected tools. "
            "Use before file, terminal, or generic catalog exploration when a request is about "
            "staff, instructors, teachers, payments, plans, schedules, or unsupported academy data. "
            "Returns whether the request can be answered from live tools now."
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
    ctx.register_tool(
        name="academy_attendance_day",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "조회 날짜. YYYY-MM-DD 형식."},
            },
            "additionalProperties": False,
        },
        handler=_attendance_day_tool_handler,
        description="Return a safe Peak attendance summary for one date, grouped by slot.",
    )
    ctx.register_tool(
        name="academy_staff_attendance_day",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "조회 날짜. YYYY-MM-DD, 오늘, 어제, 그제 등.",
                },
                "request": {
                    "type": "string",
                    "description": "원문 요청. date가 없으면 여기에서 날짜 표현을 읽는다.",
                },
            },
            "additionalProperties": False,
        },
        handler=_staff_attendance_day_tool_handler,
        description=(
            "Return PACA instructor attendance for one day from live instructor attendance records. "
            "Use for teacher/staff/instructor work-attendance questions."
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
        name="academy_prepare_write_action",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "request": {"type": "string", "description": "사용자가 반영하려는 학원 업무 원문."},
            },
            "required": ["request"],
            "additionalProperties": False,
        },
        handler=_write_action_draft_tool_handler,
        description=(
            "Draft a guarded PACA/Peak write action without mutating data. "
            "Use for payment, attendance, or record update requests before showing confirmation UI."
        ),
    )
