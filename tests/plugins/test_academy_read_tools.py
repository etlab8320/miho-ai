"""Tests for PACA/Peak academy read and safety tools."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from plugins.academy_ops.academy_query_tools import (
    _attendance_day_tool_handler,
    _capability_status_tool_handler,
    _consultation_candidates_tool_handler,
    _student_summary_tool_handler,
    _write_action_draft_tool_handler,
)
from plugins.academy_ops.staff_attendance_tool import (
    _staff_attendance_day_tool_handler,
    _staff_attendance_range_tool_handler,
)
from plugins.academy_ops.student_context_tool import _student_context_tool_handler
from plugins.academy_ops.student_records_tool import _student_record_lookup_tool_handler
from plugins.academy_ops import _capture_gateway_context
from plugins.academy_ops.student_card import AcademyStudentCardService
from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from tests.plugins.test_academy_student_card import FakeAcademyClient


class FakeCandidateRenderer:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.payloads: list[dict] = []

    def render(self, payload: dict) -> Path:
        self.payloads.append(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"png")
        return self.path


def _payload(raw: str) -> dict:
    return json.loads(raw)


def test_student_summary_tool_returns_safe_structured_card_data() -> None:
    result = _payload(
        _student_summary_tool_handler(
            {"student_query": "김민준", "period_days": 3, "today": "2026-05-25"},
            client=FakeAcademyClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "student.summary"
    assert result["card"]["profile"]["name"] == "김민준"
    assert result["card"]["attendance"]["summary"] == {"present": 1, "late": 1, "absent": 1}
    assert result["assistant_guidance"]["persona_commentary"] is True
    assert "card.risk" in result["assistant_guidance"]["use_fields"]
    dumped = json.dumps(result, ensure_ascii=False)
    assert "010-" not in dumped
    assert "500000" not in dumped
    assert "민감 메모" not in dumped


def test_student_summary_tool_requires_llm_structured_query() -> None:
    _capture_gateway_context(
        MessageEvent(
            text="고준희 학생 요약해줘",
            source=SessionSource(
                platform=Platform.DISCORD,
                user_id="discord-user-1",
                chat_id="channel-1",
                guild_id="guild-1",
            ),
        )
    )

    result = _payload(
        _student_summary_tool_handler(
            {"period_days": 3, "today": "2026-05-25"},
            client=FakeAcademyClient(),
        )
    )

    assert result["ok"] is False
    assert "학생 이름" in result["message"]


def test_student_context_tool_returns_class_days_without_guessing() -> None:
    class ContextClient(FakeAcademyClient):
        def get_student_context(self, query: str, *, today: date, period_days: int = 14) -> dict:
            assert query == "서하"
            assert today == date(2026, 5, 27)
            assert period_days == 14
            return {
                "student": {"paca_student_id": 7, "peak_student_id": 77, "name": "이서하"},
                "schedule": [
                    {"weekday": "일", "time_slot": "afternoon", "time_slot_label": "오후반"},
                    {"weekday": "수", "time_slot": "evening", "time_slot_label": "저녁반"},
                ],
                "recent_attendance": [],
                "message": "이서하 수업 요일: 일 오후반, 수 저녁반",
            }

    result = _payload(
        _student_context_tool_handler(
            {"student_query": "서하", "today": "2026-05-27", "period_days": 14},
            client=ContextClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "student.context"
    assert result["message"] == "이서하 수업 요일: 일 오후반, 수 저녁반"
    assert result["student"]["peak_student_id"] == 77
    assert result["assistant_guidance"]["avoid_hardcoded_judgment"] is True


def test_student_record_lookup_returns_exact_event_date_without_attendance_mixup() -> None:
    class RecordClient(FakeAcademyClient):
        def search_paca_students(self, query: str) -> list[dict]:
            assert query == "여민석"
            return [{"id": 301, "name": "여민석", "school": "백마고", "grade": "고2"}]

        def list_peak_students(self) -> list[dict]:
            return [{"id": 901, "paca_student_id": 301, "name": "여민석"}]

        def list_peak_records(self, peak_student_id: int) -> list[dict]:
            assert peak_student_id == 901
            return [
                {
                    "record_type_name": "제자리멀리뛰기",
                    "measured_at": "2026-05-28",
                    "value": "248",
                    "unit": "cm",
                    "direction": "higher",
                },
                {
                    "record_type_name": "배근력",
                    "measured_at": "2026-05-28",
                    "value": "132",
                    "unit": "kg",
                    "direction": "higher",
                },
                {
                    "record_type_name": "제자리멀리뛰기",
                    "measured_at": "2026-05-20",
                    "value": "242",
                    "unit": "cm",
                    "direction": "higher",
                },
            ]

    result = _payload(
        _student_record_lookup_tool_handler(
            {
                "student_query": "여민석",
                "event_query": "제멀",
                "date": "2026-05-28",
                "today": "2026-05-29",
            },
            client=RecordClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "student.record_lookup"
    assert result["student"]["name"] == "여민석"
    assert result["records"] == [
        {
            "event_name": "제자리멀리뛰기",
            "measured_at": "2026-05-28",
            "value": 248.0,
            "unit": "cm",
            "direction": "higher",
        }
    ]
    assert "여민석 2026-05-28 제멀 기록" in result["message"]
    assert "제자리멀리뛰기 248cm" in result["message"]
    assert "출석" not in result["message"]
    assert "운동계획서" not in result["message"]


def test_attendance_day_tool_summarizes_peak_slots_without_sensitive_fields() -> None:
    result = _payload(
        _attendance_day_tool_handler(
            {"date": "2026-05-25"},
            client=FakeAcademyClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "attendance.day"
    assert result["summary"] == {"present": 1, "late": 0, "absent": 0, "unknown": 0}
    assert result["slots"]["evening"][0]["student_id"] == 501
    assert "attendance_status" in result["slots"]["evening"][0]


def test_capability_status_routes_staff_attendance_to_live_tool() -> None:
    result = _payload(
        _capability_status_tool_handler(
            {"operation_key": "staff.attendance_day"},
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "capability.status"
    assert result["operation_key"] == "staff.attendance_day"
    assert result["can_execute_now"] is True
    assert result["recommended_tool"] == "academy_staff_attendance_day"


def test_staff_attendance_day_tool_reads_live_shape_without_sensitive_fields() -> None:
    class StaffClient(FakeAcademyClient):
        def list_paca_instructors(self, *, status: str = "active") -> list[dict]:
            return [
                {"id": 1, "name": "박성준", "phone": "010-1111-2222", "salary_type": "per_class"},
                {"id": 2, "name": "오철민", "phone": "010-3333-4444", "salary_type": "hourly"},
            ]

        def get_paca_instructor_attendance(self, instructor_id: int, *, year: int, month: int) -> list[dict]:
            rows = {
                1: [
                    {
                        "work_date": "2026-05-25",
                        "time_slot": "evening",
                        "attendance_status": "present",
                    }
                ],
                2: [
                    {
                        "work_date": "2026-05-24",
                        "time_slot": "evening",
                        "attendance_status": "present",
                    }
                ],
            }
            return rows[instructor_id]

    result = _payload(
        _staff_attendance_day_tool_handler(
            {"date": "2026-05-25"},
            client=StaffClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "staff.attendance_day"
    assert result["summary"]["worked"] == 1
    assert [row["name"] for row in result["instructors"]] == ["박성준"]
    dumped = json.dumps(result, ensure_ascii=False)
    assert "010-" not in dumped


def test_staff_attendance_range_tool_counts_one_instructor_month_without_sensitive_fields() -> None:
    class StaffClient(FakeAcademyClient):
        def list_paca_instructors(self, *, status: str = "active") -> list[dict]:
            return [
                {"id": 1, "name": "정의솔", "phone": "010-1111-2222"},
                {"id": 2, "name": "박성준", "phone": "010-3333-4444"},
            ]

        def get_paca_instructor_attendance(self, instructor_id: int, *, year: int, month: int) -> list[dict]:
            assert (year, month) == (2026, 5)
            rows = {
                1: [
                    {"work_date": "2026-05-20", "time_slot": "evening", "attendance_status": "present"},
                    {"work_date": "2026-05-27", "time_slot": "evening", "attendance_status": "late"},
                ],
                2: [{"work_date": "2026-05-20", "time_slot": "evening", "attendance_status": "present"}],
            }
            return rows[instructor_id]

    result = _payload(
        _staff_attendance_range_tool_handler(
            {"staff_query": "정의솔", "start_date": "2026-05-01", "end_date": "2026-05-31"},
            client=StaffClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "staff.attendance_range"
    assert result["summary"]["worked"] == 2
    assert result["instructors"][0]["name"] == "정의솔"
    assert "출근 2회" in result["message"]
    assert "010-" not in json.dumps(result, ensure_ascii=False)


def test_consultation_candidates_use_read_only_attendance_signals() -> None:
    class AttendanceClient(FakeAcademyClient):
        def list_peak_students(self) -> list[dict]:
            return [
                {"id": 501, "name": "김민준"},
                {"id": 502, "name": "박지안"},
            ]

        def get_peak_attendance(self, day: date) -> dict:
            rows = [{"student_id": 501, "attendance_status": "present"}]
            if day.isoformat() in {"2026-05-24", "2026-05-25"}:
                rows.append({"student_id": 502, "attendance_status": "absent"})
            return {"slots": {"evening": rows}}

    result = _payload(
        _consultation_candidates_tool_handler(
            {"period_days": 3, "today": "2026-05-25"},
            client=AttendanceClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "consultation.candidates"
    assert [item["name"] for item in result["candidates"]] == ["박지안"]
    assert result["candidates"][0]["signals"]["absent"] == 2
    assert result["write_enabled"] is False


def test_consultation_candidates_include_media_directive_when_candidates_exist(tmp_path) -> None:
    class AttendanceClient(FakeAcademyClient):
        def list_peak_students(self) -> list[dict]:
            return [{"id": 502, "name": "박지안"}]

        def get_peak_attendance(self, day: date) -> dict:
            return {"slots": {"evening": [{"student_id": 502, "attendance_status": "absent"}]}}

    renderer = FakeCandidateRenderer(tmp_path / "consultation.png")

    result = _payload(
        _consultation_candidates_tool_handler(
            {"period_days": 2, "today": "2026-05-25", "limit": 5},
            client=AttendanceClient(),
            renderer=renderer,
        )
    )

    assert result["ok"] is True
    assert result["image_path"] == str(tmp_path / "consultation.png")
    assert result["media_tag"] == f"MEDIA:{tmp_path / 'consultation.png'}"
    assert result["media_tag"] in result["message"]
    assert renderer.payloads[0]["candidates"][0]["name"] == "박지안"


def test_consultation_candidates_prefers_server_side_analysis() -> None:
    class ServerCandidateClient(FakeAcademyClient):
        def get_consultation_candidates(self, *, today: date, attendance_days: int = 14, limit: int = 10) -> dict:
            assert today == date(2026, 5, 27)
            assert attendance_days == 14
            assert limit == 5
            return {
                "message": "상담 후보 1명",
                "period": {
                    "attendance_start_date": "2026-05-14",
                    "end_date": "2026-05-27",
                    "attendance_days": 14,
                    "record_sample_size": 5,
                },
                "candidates": [
                    {
                        "student": {"paca_student_id": 10, "peak_student_id": 900, "name": "김민준"},
                        "priority": "high",
                        "score": 92,
                        "reasons": ["최근 14일 안에 연속 결석 2회", "최근 5개 기록 기준 하락/정체 종목 2개"],
                        "signals": {
                            "records": {
                                "problem_records": [
                                    {"event_name": "제자리멀리뛰기", "trend": "declining"},
                                    {"event_name": "10m왕복달리기", "trend": "plateau"},
                                ]
                            }
                        },
                    }
                ],
            }

        def list_peak_students(self) -> list[dict]:
            raise AssertionError("server-side endpoint should avoid local fan-out")

    result = _payload(
        _consultation_candidates_tool_handler(
            {"period_days": 14, "today": "2026-05-27", "limit": 5},
            client=ServerCandidateClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "consultation.candidates"
    assert "상담 후보 1명" in result["message"]
    assert "김민준" in result["message"]
    assert "최근 14일 안에 연속 결석 2회" in result["message"]
    assert "제자리멀리뛰기(하락)" in result["message"]
    assert "10m왕복달리기(정체)" in result["message"]
    assert result["assistant_guidance"]["instruction"].startswith("반환된 API 사실만")
    assert result["period"]["attendance_start_date"] == "2026-05-14"
    assert result["candidates"][0]["student"]["peak_student_id"] == 900
    assert "최근 14일 출결" in result["basis"]


def test_server_consultation_candidates_include_media_directive(tmp_path) -> None:
    class ServerCandidateClient(FakeAcademyClient):
        def get_consultation_candidates(self, *, today: date, attendance_days: int = 14, limit: int = 10) -> dict:
            return {
                "candidates": [
                    {
                        "student": {"paca_student_id": 10, "peak_student_id": 900, "name": "김민준"},
                        "priority": "high",
                        "score": 92,
                        "reasons": ["최근 14일 안에 연속 결석 2회"],
                    }
                ],
            }

    renderer = FakeCandidateRenderer(tmp_path / "server-consultation.png")

    result = _payload(
        _consultation_candidates_tool_handler(
            {"period_days": 14, "today": "2026-05-27", "limit": 5},
            client=ServerCandidateClient(),
            renderer=renderer,
        )
    )

    assert result["ok"] is True
    assert result["media_tag"] == f"MEDIA:{tmp_path / 'server-consultation.png'}"
    assert result["candidates"][0]["student"]["name"] == "김민준"


def test_write_action_draft_blocks_mutation_and_requires_confirmation() -> None:
    result = _payload(
        _write_action_draft_tool_handler(
            {"operation_key": "payment.mark_paid", "request": "홍길동 학원비 카드 결제 납부 완료"}
        )
    )

    assert result["ok"] is True
    assert result["operation_key"] == "payment.mark_paid"
    assert result["can_execute"] is False
    assert result["requires_confirmation"] is True
    assert result["requires_audit_log"] is True
    assert "Discord 확인 버튼" in result["blocked_reason"]
    assert "student" in result["confirmation_fields"]


def test_record_items_do_not_mix_different_names_under_same_type_id() -> None:
    class MixedRecordClient(FakeAcademyClient):
        def list_peak_records(self, peak_student_id: int) -> list[dict]:
            return [
                {
                    "record_type_id": 1,
                    "record_type_name": "제자리멀리뛰기",
                    "measured_at": "2026-05-20",
                    "value": "245",
                    "unit": "cm",
                },
                {
                    "record_type_id": 1,
                    "record_type_name": "20m 왕복달리기",
                    "measured_at": "2026-05-21",
                    "value": "62",
                    "unit": "회",
                },
            ]

    card = AcademyStudentCardService(MixedRecordClient()).build(
        "김민준",
        today=date(2026, 5, 25),
        period_days=3,
    )

    assert [item.event_name for item in card.records] == ["20m 왕복달리기", "제자리멀리뛰기"]
