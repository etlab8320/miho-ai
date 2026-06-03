"""Tests for Peak student record lookup edge cases."""

from __future__ import annotations

import json

from plugins.academy_ops.student_records_tool import _student_record_lookup_tool_handler
from tests.plugins.test_academy_student_card import FakeAcademyClient


def _payload(raw: str) -> dict:
    return json.loads(raw)


def test_student_record_lookup_recovers_recent_records_when_today_window_is_empty() -> None:
    class RecordClient(FakeAcademyClient):
        def search_paca_students(self, query: str) -> list[dict]:
            assert query == "김동혁"
            return [{"id": 302, "name": "김동혁", "school": "일산고", "grade": "고3"}]

        def list_peak_students(self) -> list[dict]:
            return [{"id": 902, "paca_student_id": 302, "name": "김동혁"}]

        def list_peak_records(self, peak_student_id: int) -> list[dict]:
            assert peak_student_id == 902
            return [
                {
                    "record_type_name": "제자리멀리뛰기",
                    "measured_at": "2026-05-30",
                    "value": "250",
                    "unit": "cm",
                    "direction": "higher",
                }
            ]

    result = _payload(
        _student_record_lookup_tool_handler(
            {
                "student_query": "김동혁",
                "event_query": "",
                "date": "2026-06-03",
                "today": "2026-06-03",
                "period_days": 30,
                "fallback_recent_when_empty": True,
            },
            client=RecordClient(),
        )
    )

    assert result["ok"] is True
    assert result["date"] == ""
    assert result["period_days"] == 30
    assert result["records"][0]["measured_at"] == "2026-05-30"
    assert "김동혁 최근 실기 기록" in result["message"]
    assert "제자리멀리뛰기 250cm" in result["message"]
