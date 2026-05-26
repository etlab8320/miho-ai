"""Tests for PACA academy schedule and consultation tools."""

from __future__ import annotations

import json
from datetime import date

from miho_cli.plugins import PluginContext, PluginManager, PluginManifest
from plugins.academy_ops import register
from plugins.academy_ops.academy_calendar_tool import (
    _academy_schedule_range_tool_handler,
    _consultation_schedule_range_tool_handler,
)
from plugins.academy_ops.quick_router import quick_command_for


def _payload(raw: str) -> dict:
    return json.loads(raw)


class CalendarClient:
    def get_paca_academy_events(self, start_day: date, end_day: date) -> list[dict]:
        assert start_day == date(2026, 5, 1)
        assert end_day == date(2026, 5, 31)
        return [
            {
                "id": 1,
                "event_date": "2026-05-23",
                "event_type": "academy",
                "title": "맥스컵",
                "start_time": "00:00:00",
                "end_time": "00:00:00",
            },
            {
                "id": 2,
                "event_date": "2026-05-29",
                "event_type": "academy",
                "title": "월말 테스트",
                "start_time": "00:00:00",
                "end_time": "00:00:00",
            },
            {
                "id": 3,
                "event_date": "2026-06-01",
                "event_type": "work",
                "title": "범위 밖",
            },
        ]

    def list_paca_consultations(self) -> list[dict]:
        return [
            {
                "id": 11,
                "consultation_type": "new_registration",
                "student_name": "김민준",
                "student_grade": "고3",
                "student_school": "맥스고",
                "parent_phone": "010-1111-2222",
                "preferred_date": "2026-05-27",
                "preferred_time": "14:00:00",
                "status": "confirmed",
                "checklist": [{"text": "민감 체크"}],
            },
            {
                "id": 12,
                "consultation_type": "re_registration",
                "student_name": "박지안",
                "preferred_date": "2026-05-28",
                "preferred_time": "16:00:00",
                "status": "confirmed",
            },
            {
                "id": 13,
                "consultation_type": "new_registration",
                "student_name": "취소학생",
                "preferred_date": "2026-05-29",
                "preferred_time": "16:00:00",
                "status": "cancelled",
            },
        ]


def test_academy_schedule_range_tool_uses_academy_events_not_class_schedules() -> None:
    result = _payload(
        _academy_schedule_range_tool_handler(
            {"start_date": "2026-05-01", "end_date": "2026-05-31"},
            client=CalendarClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "academy.schedule_range"
    assert result["summary"] == {"total": 2, "work": 0, "academy": 2, "holiday": 0, "other": 0}
    assert [row["title"] for row in result["schedules"]] == ["맥스컵", "월말 테스트"]
    assert "학원일정 2건" in result["message"]
    assert "05-23 학원일정: 맥스컵" in result["message"]
    assert "05-29 학원일정: 월말 테스트" in result["message"]


def test_consultation_schedule_range_tool_filters_new_registration_and_sensitive_fields() -> None:
    result = _payload(
        _consultation_schedule_range_tool_handler(
            {
                "start_date": "2026-05-25",
                "end_date": "2026-05-31",
                "new_registration_only": True,
            },
            client=CalendarClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "consultation.schedule_range"
    assert result["summary"] == {"total": 1, "confirmed": 1}
    assert [row["student_name"] for row in result["consultations"]] == ["김민준"]
    dumped = json.dumps(result, ensure_ascii=False)
    assert "010-" not in dumped
    assert "민감 체크" not in dumped
    assert "취소학생" not in dumped


def test_calendar_tools_require_llm_resolved_date_range() -> None:
    result = _payload(_academy_schedule_range_tool_handler({"request": "5월 학원 일정"}, client=CalendarClient()))

    assert result["ok"] is False
    assert "YYYY-MM-DD" in result["message"]


def test_natural_calendar_requests_are_not_quick_rewritten() -> None:
    assert quick_command_for("5월 학원 일정좀 봐줘") == ""
    assert quick_command_for("이번주 신규 상담일정좀 봐줘") == ""


def test_plugin_registers_calendar_tools() -> None:
    manager = PluginManager()
    manifest = PluginManifest(name="academy_ops", source="bundled", key="academy_ops")
    ctx = PluginContext(manifest, manager)

    register(ctx)

    assert "academy_schedule_range" in manager._plugin_tool_names
    assert "academy_consultation_schedule_range" in manager._plugin_tool_names
