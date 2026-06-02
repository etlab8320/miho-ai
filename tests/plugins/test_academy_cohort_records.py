"""Tests for current-enrolled cohort latest Peak record aggregation."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from plugins.academy_ops.student_record_cohort_tool import _student_record_cohort_tool_handler
from tests.plugins.academy_router_helpers import router_execute


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


def test_student_record_cohort_latest_groups_current_students_by_gender() -> None:
    class Client:
        def search_paca_students(self, query: str) -> list[dict]:
            assert query == ""
            return [
                {"id": 101, "name": "김남준", "gender": "male", "school": "일산고", "grade": "고3", "status": "active"},
                {"id": 102, "name": "이여름", "gender": "female", "school": "정발고", "grade": "고2", "status": "active"},
                {"id": 103, "name": "휴원생", "gender": "male", "status": "inactive"},
            ]

        def list_peak_students(self) -> list[dict]:
            return [
                {"id": 501, "paca_student_id": 101, "name": "김남준"},
                {"id": 502, "paca_student_id": 102, "name": "이여름"},
                {"id": 503, "paca_student_id": 103, "name": "휴원생"},
            ]

        def list_peak_records(self, peak_student_id: int) -> list[dict]:
            return {
                501: [
                    {"record_type_name": "제자리멀리뛰기", "measured_at": "2026-06-01", "value": "280", "unit": "cm"},
                    {"record_type_name": "제자리멀리뛰기", "measured_at": "2026-05-01", "value": "270", "unit": "cm"},
                ],
                502: [{"record_type_name": "제자리멀리뛰기", "measured_at": "2026-05-30", "value": "220", "unit": "cm"}],
                503: [{"record_type_name": "제자리멀리뛰기", "measured_at": "2026-06-01", "value": "300", "unit": "cm"}],
            }[peak_student_id]

    result = json.loads(
        _student_record_cohort_tool_handler({"event_query": "제멀", "limit": 50}, client=Client())
    )

    assert result["ok"] is True
    assert result["operation"] == "student.record_cohort_latest"
    assert result["summary"]["current_students"] == 2
    assert result["summary"]["students_with_records"] == 2
    assert result["summary"]["male_average"] == 280.0
    assert result["summary"]["female_average"] == 220.0
    assert [row["name"] for row in result["groups"]["male"]["rows"]] == ["김남준"]
    assert [row["name"] for row in result["groups"]["female"]["rows"]] == ["이여름"]
    assert "휴원생" not in json.dumps(result, ensure_ascii=False)
    assert "5월 월말테스트" not in result["message"]


@pytest.mark.asyncio
async def test_current_student_latest_record_request_routes_to_cohort_tool() -> None:
    calls: list[dict] = []

    async def resolver(messages: list[dict[str, str]]) -> object:
        prompt = "\n".join(message["content"] for message in messages)
        assert "academy_student_record_cohort_latest" in prompt
        return _Response(
            router_execute(
                "academy_student_record_cohort_latest",
                {"event_query": "제자리멀리뛰기", "limit": 80},
                intent="current enrolled cohort latest record average and roster",
                evidence=["현재 재원생", "최근기록", "남여 따로", "명단"],
                confidence=0.97,
            )
        )

    def handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps({"ok": True, "message": "재원생 최신 제멀 남자 평균 280cm, 여자 평균 220cm"}, ensure_ascii=False)

    route = await resolve_and_execute_academy_request(
        "현재 재원생들 남여 따로 제멀 최근기록 평균이랑 기록 명단줘",
        resolver=resolver,
        handlers={"academy_student_record_cohort_latest": handler},
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [{"event_query": "제자리멀리뛰기", "limit": 80}]
    assert "재원생 최신 제멀" in route.response_text
