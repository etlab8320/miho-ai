"""Tests for PACA/Peak academy read and safety tools."""

from __future__ import annotations

import json
from datetime import date

from plugins.academy_ops.academy_query_tools import (
    _attendance_day_tool_handler,
    _consultation_candidates_tool_handler,
    _student_summary_tool_handler,
    _write_action_draft_tool_handler,
)
from plugins.academy_ops.student_card import AcademyStudentCardService
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


def test_write_action_draft_blocks_mutation_and_requires_confirmation() -> None:
    result = _payload(
        _write_action_draft_tool_handler(
            {"request": "홍길동 학원비 카드 결제 납부 완료"}
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
