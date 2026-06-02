"""Tests for PACA class-schedule roster tool (오늘 출석할 학생 — class_schedules)."""

from __future__ import annotations

import json
from datetime import date

from miho_cli.plugins import PluginContext, PluginManager, PluginManifest
from plugins.academy_ops import register
from plugins.academy_ops.academy_calendar_tool import _class_roster_range_tool_handler


def _payload(raw: str) -> dict:
    return json.loads(raw)


class RosterClient:
    def list_paca_schedules(self, start_day: date, end_day: date) -> list[dict]:
        assert start_day == date(2026, 5, 31)
        assert end_day == date(2026, 5, 31)
        return [
            {
                "id": 616,
                "class_date": "2026-05-31",
                "time_slot": "evening",
                "title": "저녁반",
                "instructor_name": "최강사",
                "attendance_taken": False,
                "student_count": 2,
                "trial_count": 1,
            },
            {
                "id": 722,
                "class_date": "2026-05-31",
                "time_slot": "afternoon",
                "title": "오후반",
                "instructor_name": "김강사",
                "attendance_taken": False,
                "student_count": 1,
                "trial_count": 0,
            },
            {
                "id": 999,
                "class_date": "2026-06-02",
                "time_slot": "morning",
                "title": "범위 밖",
            },
        ]

    def get_paca_schedule_attendance(self, schedule_id: int) -> dict:
        # PACA's schedule-attendance payload carries NO school/grade — those come
        # from the student record and are joined in by search_paca_students.
        rosters = {
            616: {
                "students": [
                    {
                        "student_id": 301,
                        "student_name": "강도훈",
                        "is_trial": True,
                        "attendance_status": None,
                    },
                    {
                        "student_id": 302,
                        "student_name": "백지민",
                        "is_trial": False,
                        "attendance_status": None,
                    },
                ]
            },
            722: {
                "students": [
                    {
                        "student_id": 303,
                        "student_name": "이서준",
                        "is_trial": False,
                        "attendance_status": "present",
                    }
                ]
            },
        }
        return rosters.get(schedule_id, {"students": []})

    def search_paca_students(self, query: str) -> list[dict]:
        assert query == ""
        return [
            {"id": 301, "name": "강도훈", "school": "풍동고", "grade": "고3"},
            {"id": 302, "name": "백지민", "school": "백양고", "grade": "N수"},
            {"id": 303, "name": "이서준", "school": "주엽고", "grade": "고2"},
        ]


def test_class_roster_range_returns_class_schedules_with_student_rosters() -> None:
    result = _payload(
        _class_roster_range_tool_handler(
            {"start_date": "2026-05-31", "end_date": "2026-05-31"},
            client=RosterClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "class.roster_range"
    # Out-of-range schedule (2026-06-02) dropped; ordered by slot (afternoon < evening).
    assert [row["id"] for row in result["schedules"]] == [722, 616]
    assert result["summary"] == {"classes": 2, "students": 3, "trial": 1}
    # Trial student sorts first within a class.
    evening = next(row for row in result["schedules"] if row["id"] == 616)
    assert [s["name"] for s in evening["students"]] == ["강도훈", "백지민"]
    assert evening["students"][0]["is_trial"] is True
    # School/grade are absent from the attendance payload and joined in from the
    # student roster (search_paca_students) by student_id.
    assert evening["students"][0]["school"] == "풍동고"
    assert evening["students"][0]["grade"] == "고3"
    assert evening["students"][1]["school"] == "백양고"
    afternoon = next(row for row in result["schedules"] if row["id"] == 722)
    assert afternoon["students"][0]["school"] == "주엽고"
    assert afternoon["students"][0]["grade"] == "고2"
    assert "수업 2건" in result["message"]
    assert "강도훈" in result["message"]
    assert "백지민" in result["message"]
    # Enriched school/grade must surface in the LLM-facing message too.
    assert "풍동고" in result["message"]
    assert "고3" in result["message"]


class _NoProfileClient:
    """A client whose roster carries no school/grade (real PACA shape) AND
    cannot look up student profiles. Enrichment must degrade gracefully —
    blank school/grade, never a crash."""

    def list_paca_schedules(self, start_day: date, end_day: date) -> list[dict]:
        return [{"id": 722, "class_date": "2026-05-31", "time_slot": "afternoon", "student_count": 1}]

    def get_paca_schedule_attendance(self, schedule_id: int) -> dict:
        return {"students": [{"student_id": 303, "student_name": "이서준", "is_trial": False}]}


def test_class_roster_degrades_when_profiles_unavailable() -> None:
    result = _payload(
        _class_roster_range_tool_handler(
            {"start_date": "2026-05-31", "end_date": "2026-05-31"},
            client=_NoProfileClient(),
        )
    )
    assert result["ok"] is True
    student = result["schedules"][0]["students"][0]
    assert student["name"] == "이서준"
    assert student["school"] == ""
    assert student["grade"] == ""


def test_class_roster_range_can_skip_roster_and_use_counts() -> None:
    result = _payload(
        _class_roster_range_tool_handler(
            {"start_date": "2026-05-31", "end_date": "2026-05-31", "with_roster": False},
            client=RosterClient(),
        )
    )

    assert result["ok"] is True
    assert result["with_roster"] is False
    # No per-schedule roster fetched; counts come from list_paca_schedules.
    assert all("students" not in row for row in result["schedules"])
    assert result["summary"] == {"classes": 2, "students": 3, "trial": 1}


def test_class_roster_range_requires_llm_resolved_date_range() -> None:
    result = _payload(_class_roster_range_tool_handler({"request": "오늘 출석할 학생"}, client=RosterClient()))

    assert result["ok"] is False
    assert "YYYY-MM-DD" in result["message"]


def test_plugin_registers_class_roster_tool() -> None:
    manager = PluginManager()
    manifest = PluginManifest(name="academy_ops", source="bundled", key="academy_ops")
    ctx = PluginContext(manifest, manager)

    register(ctx)

    assert "academy_class_roster_range" in manager._plugin_tool_names


class _EmptySlotClient:
    """PACA auto-creates a slot per time-of-day; an unused slot has
    student_count 0 but its attendance endpoint still returns the season's
    enrolled students (a phantom roster). The roster must drop such slots."""

    def list_paca_schedules(self, start_day: date, end_day: date) -> list[dict]:
        return [
            {"id": 722, "class_date": "2026-05-31", "time_slot": "afternoon", "student_count": 10, "trial_count": 0},
            {"id": 616, "class_date": "2026-05-31", "time_slot": "evening", "student_count": 0, "trial_count": 0},
        ]

    def get_paca_schedule_attendance(self, schedule_id: int) -> dict:
        # Both slots would return the same season roster (the bug). The
        # zero-count evening slot must be excluded before this is even reached.
        return {"students": [{"student_id": 1, "student_name": "백지민", "is_trial": False}]}


def test_class_roster_excludes_empty_auto_slots() -> None:
    result = _payload(
        _class_roster_range_tool_handler(
            {"start_date": "2026-05-31", "end_date": "2026-05-31"},
            client=_EmptySlotClient(),
        )
    )
    assert result["ok"] is True
    # evening (student_count 0, phantom season roster) dropped; only afternoon.
    assert [row["id"] for row in result["schedules"]] == [722]
    assert result["summary"]["classes"] == 1
