"""Tests for duplicate and resilient PACA student lookup across academy tools."""

from __future__ import annotations

import json
from datetime import date

from plugins.academy_ops.student_attendance_tool import _student_attendance_range_tool_handler
from plugins.academy_ops.student_card import AcademyStudentCardService
from plugins.academy_ops.student_lookup import resolve_paca_student


def _payload(raw: str) -> dict:
    return json.loads(raw)


class DuplicateStudentClient:
    def search_paca_students(self, query: str) -> list[dict]:
        if query == "박시현":
            return [
                {
                    "id": 9228,
                    "name": "박시현",
                    "gender": "",
                    "school": "서정고",
                    "grade": "N수",
                    "status": "active",
                    "weekly_count": 3,
                    "time_slot": "evening",
                    "class_days": [{"day": 1, "timeSlot": "evening"}],
                },
                {
                    "id": 58,
                    "name": "박시현",
                    "gender": "",
                    "school": "고양일고등학교",
                    "grade": "고3",
                    "status": "pending",
                    "weekly_count": 0,
                    "time_slot": "evening",
                    "class_days": [],
                },
            ]
        return []

    def get_paca_student_detail(self, paca_student_id: int) -> dict:
        assert paca_student_id == 9228
        return {"student": self.search_paca_students("박시현")[0], "payments": []}

    def get_paca_student_attendance(self, paca_student_id: int, *, year_month: str) -> dict:
        assert paca_student_id == 9228
        assert year_month == "2026-05"
        return {"records": []}

    def list_paca_schedules(self, start_day: date, end_day: date) -> list[dict]:
        assert start_day == date(2026, 5, 1)
        assert end_day == date(2026, 5, 31)
        return [{"class_date": "2026-05-04", "time_slot": "evening", "student_count": 10}]

    def list_peak_students(self) -> list[dict]:
        return [{"id": 501, "paca_student_id": 9228, "name": "박시현"}]

    def list_peak_records(self, peak_student_id: int) -> list[dict]:
        assert peak_student_id == 501
        return []


def test_attendance_lookup_resolves_school_or_grade_with_duplicate_names() -> None:
    for student_query in ("서정고 박시현", "N수 박시현"):
        result = _payload(
            _student_attendance_range_tool_handler(
                {
                    "student_query": student_query,
                    "start_date": "2026-05-01",
                    "end_date": "2026-05-31",
                    "today": "2026-05-28",
                },
                client=DuplicateStudentClient(),
            )
        )

        assert result["ok"] is True
        assert result["student"]["paca_student_id"] == 9228
        assert result["student"]["school"] == "서정고"
        assert result["student"]["grade"] == "N수"


def test_student_card_lookup_resolves_school_with_duplicate_names() -> None:
    card = AcademyStudentCardService(DuplicateStudentClient()).build(
        "서정고 박시현",
        today=date(2026, 5, 25),
        period_days=3,
    )

    assert card.profile.paca_student_id == 9228
    assert card.profile.school == "서정고"
    assert card.profile.grade == "N수"


def test_student_lookup_recovers_single_hangul_typo_with_suffix() -> None:
    class Client:
        def search_paca_students(self, query: str) -> list[dict]:
            return []

        def list_paca_students(self, *, status: str = "") -> list[dict]:
            assert status == "active"
            return [
                {"id": 1, "name": "김동혁", "school": "일산고"},
                {"id": 2, "name": "박동혁", "school": "강남고"},
            ]

    student = resolve_paca_student(Client(), "깅동혁학생")

    assert student["name"] == "김동혁"
