"""Tests for PACA/Peak academy read and safety tools."""

from __future__ import annotations

import json
from datetime import date

from plugins.academy_ops.academy_query_tools import (
    _attendance_day_tool_handler,
    _capability_status_tool_handler,
    _consultation_candidates_tool_handler,
    _staff_attendance_day_tool_handler,
    _student_summary_tool_handler,
    _write_action_draft_tool_handler,
)
from plugins.academy_ops import _capture_gateway_context
from plugins.academy_ops.student_card import AcademyStudentCardService
from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from tests.plugins.test_academy_student_card import FakeAcademyClient


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
