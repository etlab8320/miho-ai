"""Tests for the read-only generic PACA/Peak API query tool."""

from __future__ import annotations

import json

from plugins.academy_ops.api_query_tool import (
    MAX_RESULT_CHARS,
    _api_query_tool_handler,
)


class StubClient:
    def list_paca_students(self, *, status: str = "") -> list[dict]:
        assert status == "active"
        return [
            {"id": 1, "name": "김민준", "status": "active", "created_at": "2026-03-02"},
            {"id": 2, "name": "이서하", "status": "active", "created_at": "2026-04-15"},
        ]

    def get_paca_academy_events(self, start_day, end_day) -> list[dict]:
        return [{"title": "맥스컵", "start": start_day.isoformat(), "end": end_day.isoformat()}]


def _run(args: dict, client: object) -> dict:
    return json.loads(_api_query_tool_handler(args, client=client))


def test_api_query_dispatches_listed_method_with_params() -> None:
    payload = _run({"method": "list_paca_students", "params": {"status": "active"}}, StubClient())
    assert payload["ok"] is True
    assert [row["name"] for row in payload["result"]] == ["김민준", "이서하"]


def test_api_query_coerces_date_params() -> None:
    payload = _run(
        {"method": "get_paca_academy_events", "params": {"start_date": "2026-01-01", "end_date": "2026-06-30"}},
        StubClient(),
    )
    assert payload["ok"] is True
    assert payload["result"][0]["start"] == "2026-01-01"


def test_api_query_rejects_unknown_method() -> None:
    payload = _run({"method": "drop_paca_students"}, StubClient())
    assert payload["ok"] is False
    assert "지원하지 않는 method" in payload["message"]


def test_api_query_reports_missing_required_param() -> None:
    payload = _run({"method": "get_paca_academy_events", "params": {"start_date": "2026-01-01"}}, StubClient())
    assert payload["ok"] is False
    assert "end_date" in payload["message"]


def test_api_query_rejects_malformed_date() -> None:
    payload = _run(
        {"method": "get_paca_academy_events", "params": {"start_date": "올해초", "end_date": "2026-06-30"}},
        StubClient(),
    )
    assert payload["ok"] is False
    assert "YYYY-MM-DD" in payload["message"]


def test_api_query_truncates_oversized_list_results() -> None:
    class BigClient:
        def list_paca_students(self, *, status: str = "") -> list[dict]:
            return [{"id": i, "memo": "x" * 200} for i in range(500)]

    payload = _run({"method": "list_paca_students"}, BigClient())
    assert payload["ok"] is True
    assert payload["truncated"] is True
    assert payload["total_items"] == 500
    assert payload["shown_items"] < 500
    assert len(json.dumps(payload, ensure_ascii=False)) < MAX_RESULT_CHARS + 1_000
