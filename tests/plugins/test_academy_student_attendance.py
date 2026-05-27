"""Tests for student attendance range lookup."""

from __future__ import annotations

from datetime import date
import json

from miho_cli.plugins import PluginContext, PluginManager, PluginManifest
from plugins.academy_ops import register
from plugins.academy_ops.academy_query_tools import _capability_status_tool_handler
from plugins.academy_ops.attendance_calendar_template import render_attendance_calendar_html
from plugins.academy_ops.attendance_calendar_tool import _student_attendance_calendar_image_tool_handler
from plugins.academy_ops.commentary_config import COMMENTARY_MODEL
from plugins.academy_ops.student_attendance_tool import _student_attendance_range_tool_handler


def _payload(raw: str) -> dict:
    return json.loads(raw)


class StudentAttendanceClient:
    def search_paca_students(self, query: str) -> list[dict]:
        assert query == "김민준"
        return [
            {
                "id": 101,
                "name": "김민준",
                "school": "백마고",
                "grade": "고3",
                "phone": "010-1111-2222",
                "time_slot": "evening",
                "class_days": [
                    {"day": 5, "timeSlot": "evening"},
                    {"day": 6, "timeSlot": "evening"},
                    {"day": 0, "timeSlot": "afternoon"},
                    {"day": 1, "timeSlot": "evening"},
                ],
            }
        ]

    def get_paca_student_attendance(self, paca_student_id: int, *, year_month: str) -> dict:
        assert paca_student_id == 101
        assert year_month == "2026-05"
        return {
            "records": [
                {"date": "2026-05-01", "time_slot": "evening", "attendance_status": "present", "phone": "010-2222-3333"},
                {"date": "2026-05-02", "time_slot": "evening", "attendance_status": "late"},
                {"date": "2026-05-03", "time_slot": "afternoon", "attendance_status": "absent", "notes": "개인사정"},
            ]
        }

    def list_paca_schedules(self, start_day: date, end_day: date) -> list[dict]:
        assert start_day == date(2026, 5, 1)
        assert end_day == date(2026, 5, 4)
        return [
            {"class_date": "2026-05-01", "time_slot": "evening", "student_count": 10},
            {"class_date": "2026-05-02", "time_slot": "evening", "student_count": 10},
            {"class_date": "2026-05-03", "time_slot": "afternoon", "student_count": 10},
            {"class_date": "2026-05-03", "time_slot": "evening", "student_count": 0},
            {"class_date": "2026-05-04", "time_slot": "evening", "student_count": 10},
        ]


class SundayAfternoonClient(StudentAttendanceClient):
    def get_paca_student_attendance(self, paca_student_id: int, *, year_month: str) -> dict:
        assert paca_student_id == 101
        assert year_month == "2026-05"
        return {"records": []}

    def list_paca_schedules(self, start_day: date, end_day: date) -> list[dict]:
        assert start_day == date(2026, 5, 3)
        assert end_day == date(2026, 5, 3)
        return [
            {"class_date": "2026-05-03", "time_slot": "afternoon", "student_count": 10},
            {"class_date": "2026-05-03", "time_slot": "evening", "student_count": 0},
        ]


class FutureUncheckedRecordClient(StudentAttendanceClient):
    def get_paca_student_attendance(self, paca_student_id: int, *, year_month: str) -> dict:
        assert paca_student_id == 101
        assert year_month == "2026-05"
        return {
            "records": [
                {"date": "2026-05-01", "time_slot": "evening", "attendance_status": "present"},
                {"date": "2026-05-04", "time_slot": "evening", "attendance_status": "unchecked"},
            ]
        }

    def list_paca_schedules(self, start_day: date, end_day: date) -> list[dict]:
        assert start_day == date(2026, 5, 4)
        assert end_day == date(2026, 5, 4)
        return [{"class_date": "2026-05-04", "time_slot": "evening", "student_count": 10}]


class FakeCalendarRenderer:
    def __init__(self, path) -> None:
        self.path = path
        self.payloads: list[dict] = []

    def render(self, payload: dict):
        self.payloads.append(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"png")
        return self.path


def test_student_attendance_range_returns_safe_counts_and_michekeu_label() -> None:
    result = _payload(
        _student_attendance_range_tool_handler(
            {"student_query": "김민준", "start_date": "2026-05-01", "end_date": "2026-05-04"},
            client=StudentAttendanceClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "attendance.student_month"
    assert result["summary"] == {
        "present": 1,
        "late": 1,
        "absent": 1,
        "excused": 0,
        "makeup": 0,
        "unchecked": 1,
        "upcoming": 0,
        "no_class": 0,
        "checked": 3,
        "scheduled": 4,
        "attendance_rate": 66.7,
    }
    assert [row["status"] for row in result["attendance"]] == ["present", "late", "absent", "unchecked"]
    assert result["attendance"][2]["time_slot"] == "afternoon"
    assert result["attendance"][3]["time_slot"] == "evening"
    assert "미체크 1회" in result["message"]
    assert "수업없음 0일" in result["message"]
    assert "미확인" not in result["message"]
    assert result["assistant_guidance"] == {
        "persona_commentary": True,
        "preferred_fast_model": COMMENTARY_MODEL,
        "avoid_hardcoded_judgment": True,
        "instruction": (
            "반환된 API 사실만 바탕으로 미호 말투의 짧은 코멘트를 작성해. "
            "없는 사실, 고정 판단, 템플릿 문장을 만들지 마. "
            "message는 사실 요약 원문으로만 참고하고, 그대로 복붙하지 말고 간단히 해석해."
        ),
        "unchecked_label": "미체크",
        "do_not_use_labels": ["미확인"],
    }
    dumped = json.dumps(result, ensure_ascii=False)
    assert "010-" not in dumped


def test_student_attendance_range_requires_explicit_dates() -> None:
    result = _payload(
        _student_attendance_range_tool_handler(
            {"student_query": "김민준", "request": "김민준 5월 출석"},
            client=StudentAttendanceClient(),
        )
    )

    assert result["ok"] is False
    assert "YYYY-MM-DD" in result["message"]


def test_student_attendance_range_uses_api_schedule_for_sunday_afternoon() -> None:
    result = _payload(
        _student_attendance_range_tool_handler(
            {"student_query": "김민준", "start_date": "2026-05-03", "end_date": "2026-05-03"},
            client=SundayAfternoonClient(),
        )
    )

    assert result["ok"] is True
    assert result["attendance"][0]["status"] == "unchecked"
    assert result["attendance"][0]["time_slot"] == "afternoon"
    assert result["summary"]["scheduled"] == 1


def test_student_attendance_range_excludes_future_classes_from_michekeu() -> None:
    result = _payload(
        _student_attendance_range_tool_handler(
            {
                "student_query": "김민준",
                "start_date": "2026-05-01",
                "end_date": "2026-05-04",
                "today": "2026-05-03",
            },
            client=StudentAttendanceClient(),
        )
    )

    assert result["ok"] is True
    assert result["attendance"][3]["status"] == "upcoming"
    assert result["summary"]["unchecked"] == 0
    assert result["summary"]["upcoming"] == 1
    assert "미체크 0회" in result["message"]
    assert "예정 수업일 1일" in result["message"]


def test_student_attendance_range_converts_future_unchecked_api_records_to_upcoming() -> None:
    result = _payload(
        _student_attendance_range_tool_handler(
            {
                "student_query": "김민준",
                    "start_date": "2026-05-04",
                "end_date": "2026-05-04",
                "today": "2026-05-03",
            },
            client=FutureUncheckedRecordClient(),
        )
    )

    assert result["ok"] is True
    assert result["attendance"][0]["status"] == "upcoming"
    assert result["summary"]["unchecked"] == 0
    assert result["summary"]["upcoming"] == 1
    assert "미체크 0회" in result["message"]


def test_student_attendance_calendar_html_marks_classes_without_no_class_label() -> None:
    payload = _payload(
        _student_attendance_range_tool_handler(
            {"student_query": "김민준", "start_date": "2026-05-01", "end_date": "2026-05-04"},
            client=StudentAttendanceClient(),
        )
    )

    html = render_attendance_calendar_html(payload)

    assert "2026년 5월 출석 달력" in html
    assert "&hearts;" in html
    assert "출석" in html
    assert "지각" in html
    assert "결석" in html
    assert "미체크" in html
    assert "수업없는 날과 아직 오지 않은 날은 별도 표시하지 않았어" in html
    assert "수업없음" not in html
    assert "010-" not in html


def test_student_attendance_calendar_hides_future_unchecked_days() -> None:
    payload = {
        "student": {"name": "김민준", "school": "백마고", "grade": "고3"},
        "start_date": "2026-05-01",
        "end_date": "2026-05-04",
        "summary": {"present": 1, "late": 0, "absent": 0, "unchecked": 1},
        "attendance": [
            {"date": "2026-05-01", "status": "present", "time_slot": "evening"},
            {"date": "2026-05-04", "status": "unchecked", "time_slot": "evening"},
        ],
    }

    html = render_attendance_calendar_html(payload, today=date(2026, 5, 3))

    assert "badge unchecked" not in html
    assert "<b>0</b><span>미체크</span>" in html
    assert "아직 오지 않은 날은 별도 표시하지 않았어" in html


def test_student_attendance_calendar_tool_returns_media_tag(tmp_path) -> None:
    renderer = FakeCalendarRenderer(tmp_path / "attendance.png")
    result = _payload(
        _student_attendance_calendar_image_tool_handler(
            {"student_query": "김민준", "start_date": "2026-05-01", "end_date": "2026-05-04"},
            client=StudentAttendanceClient(),
            renderer=renderer,
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "attendance.student_calendar_image"
    assert result["media_tag"] == f"MEDIA:{tmp_path / 'attendance.png'}"
    assert result["image_path"] == str(tmp_path / "attendance.png")
    assert "출석 달력이야" in result["message"]
    assert result["today"]
    assert renderer.payloads[0]["summary"]["present"] == 1


def test_capability_status_recommends_student_attendance_tool() -> None:
    result = _payload(_capability_status_tool_handler({"operation_key": "attendance.student_month"}))

    assert result["ok"] is True
    assert result["operation_key"] == "attendance.student_month"
    assert result["can_execute_now"] is True
    assert result["recommended_tool"] == "academy_student_attendance_range"


def test_plugin_registers_student_attendance_tool() -> None:
    manager = PluginManager()
    manifest = PluginManifest(name="academy_ops", source="bundled", key="academy_ops")
    ctx = PluginContext(manifest, manager)

    register(ctx)

    assert "academy_student_attendance_range" in manager._plugin_tool_names
    assert "academy_student_attendance_calendar_image" in manager._plugin_tool_names
