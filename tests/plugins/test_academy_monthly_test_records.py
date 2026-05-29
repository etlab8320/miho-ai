"""Tests for Peak monthly assessment record aggregates."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from plugins.academy_ops.academy_api import AcademyApiClient
from plugins.academy_ops.monthly_test_records_tool import _monthly_test_records_tool_handler
from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request
from tests.plugins.academy_router_helpers import router_execute


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [SimpleNamespace(message=SimpleNamespace(content=content))]


class MonthlyClient:
    def list_peak_monthly_tests(self) -> list[dict]:
        return [
            {
                "id": 13,
                "test_month": "2026-05",
                "test_name": "2026년 5월 월말 평가",
                "status": "active",
            }
        ]

    def get_peak_monthly_test_records(self, monthly_test_id: int) -> dict:
        assert monthly_test_id == 13
        return {
            "test": {
                "id": 13,
                "test_month": "2026-05",
                "test_name": "2026년 5월 월말 평가",
                "status": "active",
            },
            "record_types": [
                {"record_type_id": 1, "name": "제자리멀리뛰기", "unit": "cm", "direction": "higher"},
                {"record_type_id": 2, "name": "배근력", "unit": "kg", "direction": "higher"},
            ],
            "participants": [
                {"name": "남A", "gender": "M", "school": "저현고", "records": {"1": 260, "2": 120}},
                {"name": "남B", "gender": "M", "school": "문산제일고", "records": {"1": 300}},
                {"name": "남C", "gender": "M", "school": "백마고", "records": {"1": 280}},
                {"name": "여A", "gender": "F", "school": "백마고", "records": {"1": 210}},
                {"name": "여B", "gender": "F", "school": "문산제일고", "records": {"1": 230}},
                {"name": "여C", "gender": "F", "school": "정발고", "records": {"1": 220}},
            ],
        }


def _payload(raw: str) -> dict:
    return json.loads(raw)


def test_academy_api_client_reads_monthly_test_contract() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/peak/monthly-tests":
            return httpx.Response(200, json={"tests": [{"id": 13, "status": "active"}]})
        if request.url.path == "/peak/monthly-tests/13/all-records":
            return httpx.Response(200, json={"participants": [], "record_types": []})
        return httpx.Response(404, json={"error": "not found"})

    client = AcademyApiClient(
        token="token",
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
    )

    assert client.list_peak_monthly_tests() == [{"id": 13, "status": "active"}]
    assert client.get_peak_monthly_test_records(13) == {"participants": [], "record_types": []}
    assert seen == ["/peak/monthly-tests", "/peak/monthly-tests/13/all-records"]


def test_monthly_test_records_average_excludes_named_school() -> None:
    result = _payload(
        _monthly_test_records_tool_handler(
            {
                "event_query": "제멀",
                "exclude_schools": ["문산제일고"],
                "today": "2026-05-29",
            },
            client=MonthlyClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "monthly_test.records"
    assert result["test"]["id"] == 13
    assert result["event"]["name"] == "제자리멀리뛰기"
    assert result["excluded"]["count"] == 2
    assert result["summary"]["male"] == {"count": 2, "average": 270.0, "min": 260.0, "max": 280.0}
    assert result["summary"]["female"] == {"count": 2, "average": 215.0, "min": 210.0, "max": 220.0}
    assert "남학생 270cm" in result["message"]
    assert "여학생 215cm" in result["message"]


@pytest.mark.asyncio
async def test_monthly_assessment_average_routes_to_monthly_records_tool() -> None:
    calls: list[dict] = []

    async def resolver(messages: list[dict[str, str]]) -> object:
        prompt = "\n".join(message["content"] for message in messages)
        assert "academy_monthly_test_records" in prompt
        assert "키워드 하나가 아니라 전체 문맥" in prompt
        return _Response(
            router_execute(
                "academy_monthly_test_records",
                {
                    "event_query": "제자리멀리뛰기",
                    "exclude_schools": ["문산제일고"],
                    "today": "2026-05-29",
                },
                intent="monthly assessment aggregate",
                evidence=["monthly assessment context", "aggregate average", "school exclusion"],
                confidence=0.95,
            )
        )

    def monthly_handler(args: dict, **_: object) -> str:
        calls.append(args)
        return json.dumps(
            {
                "ok": True,
                "operation": "monthly_test.records",
                "message": "월말 평가 제자리멀리뛰기 평균은 남학생 270cm, 여학생 215cm야.",
            },
            ensure_ascii=False,
        )

    route = await resolve_and_execute_academy_request(
        "문산제일고 빼고 이번 월말 평가 제멀 남녀 평균 알려줘",
        resolver=resolver,
        handlers={"academy_monthly_test_records": monthly_handler},
        today="2026-05-29",
        synthesize=False,
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert calls == [
        {
            "event_query": "제자리멀리뛰기",
            "exclude_schools": ["문산제일고"],
            "today": "2026-05-29",
        }
    ]
    assert "남학생 270cm" in route.response_text


def test_matching_event_recovers_event_from_original_text(monkeypatch):
    """LLM이 event_query를 잘못 추출(테스트명 등)해도 원문에서 종목을 회수해야 한다.

    회귀 방지: '월말테스트'가 종목 슬롯에 들어가 매칭 실패하던 버그(2026-05-30).
    """
    import plugins.academy_ops.monthly_test_records_tool as mt

    record_types = [{"name": "제자리멀리뛰기", "id": 1}, {"name": "메디신볼", "id": 2}]

    def fake_best(query, names, **_):
        # 종목 신호가 있으면 0번(제자리멀리뛰기), 그 외(테스트명 등)는 abstain.
        return 0 if ("멀리" in query or query.endswith("뛰기") or "점프" in query) else None

    monkeypatch.setattr(mt.semantic_intents, "best_match_index", fake_best)

    # event_query는 종목이 아닌 테스트명 → 매칭 실패하지만 원문에서 회수.
    event = mt._matching_event(record_types, "월말테스트", fallback_text="이번 월말 멀리 평균 알려줘")
    assert event is not None and event["id"] == 1


def test_matching_event_text_fallback_without_embedding(monkeypatch):
    """임베딩 제공자가 없으면(abstain) 기존 텍스트 매칭으로 떨어진다(회귀 0)."""
    import plugins.academy_ops.monthly_test_records_tool as mt

    monkeypatch.setattr(mt.semantic_intents, "best_match_index", lambda *a, **k: None)
    record_types = [{"name": "제자리멀리뛰기", "id": 1}, {"name": "좌전굴", "id": 2}]

    # 임베딩 None → _event_matches(ordered subsequence)로 약칭 매칭.
    event = mt._matching_event(record_types, "제자리멀리")
    assert event is not None and event["id"] == 1


def test_matching_event_abstains_on_unrelated_text(monkeypatch):
    """종목과 무관한 텍스트는 임베딩·텍스트 둘 다 매칭 안 돼 None."""
    import plugins.academy_ops.monthly_test_records_tool as mt

    monkeypatch.setattr(mt.semantic_intents, "best_match_index", lambda *a, **k: None)
    record_types = [{"name": "제자리멀리뛰기", "id": 1}]
    assert mt._matching_event(record_types, "로그인", fallback_text="로그인 상태 확인") is None
