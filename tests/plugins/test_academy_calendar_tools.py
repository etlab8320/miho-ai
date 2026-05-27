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
                "id": 14,
                "consultation_type": "trial",
                "learning_type": "trial_class",
                "student_name": "이체험",
                "student_grade": "고2",
                "student_school": "체험고",
                "preferred_date": "2026-05-27",
                "preferred_time": "18:00:00",
                "status": "confirmed",
                "parent_phone": "010-3333-4444",
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


class TrialAttendanceClient(CalendarClient):
    def get_peak_attendance(self, target_day: date) -> dict:
        assert target_day == date(2026, 5, 27)
        return {
            "date": "2026-05-27",
            "slots": {
                "afternoon": [
                    {
                        "assignment_id": 21,
                        "student_id": 301,
                        "student_name": "일반학생",
                        "school": "맥스고",
                        "grade": "고3",
                        "is_trial": 0,
                    }
                ],
                "evening": [
                    {
                        "assignment_id": 22,
                        "student_id": 302,
                        "student_name": "강도훈",
                        "school": "풍동고",
                        "grade": "고3",
                        "is_trial": 1,
                    },
                    {
                        "assignment_id": 23,
                        "student_id": 303,
                        "student_name": "기아림",
                        "school": "백양고",
                        "grade": "N수",
                        "is_trial": "1",
                    },
                ],
            },
        }


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


def test_consultation_schedule_range_tool_can_filter_trial_lessons() -> None:
    result = _payload(
        _consultation_schedule_range_tool_handler(
            {
                "start_date": "2026-05-27",
                "end_date": "2026-05-27",
                "new_registration_only": False,
                "trial_only": True,
            },
            client=CalendarClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "consultation.schedule_range"
    assert result["summary"] == {"total": 1, "confirmed": 1}
    assert [row["student_name"] for row in result["consultations"]] == ["이체험"]
    assert "체험수업 일정 1건" in result["message"]
    dumped = json.dumps(result, ensure_ascii=False)
    assert "010-" not in dumped


def test_trial_lesson_schedule_uses_peak_attendance_trial_students() -> None:
    result = _payload(
        _consultation_schedule_range_tool_handler(
            {
                "start_date": "2026-05-27",
                "end_date": "2026-05-27",
                "new_registration_only": False,
                "trial_only": True,
            },
            client=TrialAttendanceClient(),
        )
    )

    assert result["ok"] is True
    assert result["summary"]["total"] == 2
    assert [row["student_name"] for row in result["consultations"]] == ["강도훈", "기아림"]
    assert all(row["time_slot"] == "evening" for row in result["consultations"])
    assert "저녁반" in result["message"]
    assert "예정" in result["message"]
    assert "scheduled" not in result["message"]
    assert "일반학생" not in json.dumps(result, ensure_ascii=False)


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
