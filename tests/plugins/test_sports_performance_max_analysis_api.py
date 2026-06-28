"""Tests for the Max academy analysis variables API tool."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any

from plugins import sports_performance
from plugins.sports_performance import max_analysis_api
from plugins.sports_performance.max_analysis_api import (
    API_KEY_ENV,
    build_max_analysis_variables_response,
    max_analysis_variables_tool_handler,
)


def _row(**overrides: Any) -> dict[str, Any]:
    row = {
        "student_name": "홍길동",
        "gender": "male",
        "age": 18,
        "height_cm": 178.0,
        "weight_kg": 72.0,
        "academy_id": "academy-1",
        "academy_name": "맥스체대입시_일산 교육원",
        "measured_at": "2026-06-01",
        "sport": "SLJ",
        "session_id": "session-1",
        "record_value": 245.0,
        "record_unit": "cm",
        "phase": "takeoff",
        "variable_key": "ankle_angle",
        "variable_name": "발목 각도",
        "variable_value": 32.1,
        "unit": "deg",
    }
    row.update(overrides)
    return row


class _Ctx:
    def __init__(self) -> None:
        self.tools: list[str] = []

    def register_tool(self, *, name: str, **_: Any) -> None:
        self.tools.append(name)

    def register_hook(self, *_args: Any, **_kwargs: Any) -> None:
        return None

    def register_auxiliary_task(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def test_max_analysis_tool_is_registered_with_plugin_yaml() -> None:
    ctx = _Ctx()

    sports_performance.register(ctx)

    yaml_text = Path("plugins/sports_performance/plugin.yaml").read_text(encoding="utf-8")
    assert "sports_max_analysis_variables" in ctx.tools
    assert "sports_max_analysis_variables" in yaml_text


def test_missing_api_key_returns_korean_plain_error(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    result = build_max_analysis_variables_response({})

    assert result["ok"] is False
    assert result["error_code"] == "missing_api_key"
    assert API_KEY_ENV in result["errors"][0]
    assert "Traceback" not in json.dumps(result, ensure_ascii=False)
    assert "401" not in json.dumps(result, ensure_ascii=False)


def test_fetches_all_academies_without_exposing_api_key(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "secret-key")
    calls: list[dict[str, Any]] = []

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> list[dict[str, Any]]:
        calls.append({"endpoint": endpoint, "params": params, "api_key": api_key, "timeout": timeout})
        return [_row()]

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)

    result = build_max_analysis_variables_response({"sport": "slj", "limit": 100, "offset": 0})

    assert result["ok"] is True
    assert result["scope"] == "all_academies"
    assert result["query"] == {"limit": 100, "offset": 0, "sport": "slj"}
    assert result["record_count"] == 1
    assert result["summary"]["variable_key_count"] == 1
    assert result["variables"][0]["variable_key"] == "ankle_angle"
    assert calls[0]["api_key"] == "secret-key"
    assert "secret-key" not in json.dumps(result, ensure_ascii=False)


def test_fetches_specific_academy_with_contract_filters(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "secret-key")
    captured: dict[str, Any] = {}

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> dict[str, Any]:
        del endpoint, api_key, timeout
        captured.update(params)
        return {"data": [_row(academy_id="academy-2", academy_name="맥스체대입시_강남 교육원")]}

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)

    result = build_max_analysis_variables_response(
        {
            "academy_id": "academy-2",
            "academy_name": "강남",
            "sport": "SPRINT",
            "from_date": "2026-06-01",
            "to_date": "2026-06-30",
        }
    )

    assert result["ok"] is True
    assert result["scope"] == "specific_academy"
    assert captured == {
        "limit": 1000,
        "offset": 0,
        "academy_id": "academy-2",
        "academy_name": "강남",
        "sport": "sprint",
        "from_date": "2026-06-01",
        "to_date": "2026-06-30",
    }


def test_korean_slj_alias_is_normalized_before_api_request(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "secret-key")
    captured: dict[str, Any] = {}

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> list[dict[str, Any]]:
        del endpoint, api_key, timeout
        captured.update(params)
        return [_row(sport="SLJ")]

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)

    result = build_max_analysis_variables_response({"sport": "제멀", "student_name": "홍길동"})

    assert result["ok"] is True
    assert captured["sport"] == "slj"
    assert result["query"]["sport"] == "slj"
    assert result["query"]["student_name"] == "홍길동"


def test_student_name_filter_keeps_only_matching_motion_analysis_records(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "secret-key")

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> list[dict[str, Any]]:
        del endpoint, api_key, timeout
        assert "student_name" not in params
        return [
            _row(student_name="강지연", measured_at="2026-06-02", session_id="session-1"),
            _row(student_name="김가온", measured_at="2026-06-03", session_id="session-2"),
            _row(student_name="강지연", measured_at="2026-06-03", session_id="session-3"),
        ]

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)

    result = build_max_analysis_variables_response({"student_name": "강지연", "sport": "slj"})

    assert result["ok"] is True
    assert result["query"]["student_name"] == "강지연"
    assert result["record_count"] == 2
    assert {row["student_name"] for row in result["records"]} == {"강지연"}
    assert result["summary"]["student_names"] == ["강지연"]
    assert result["student_filter"]["matched"] is True


def test_student_filter_result_includes_compact_session_summaries(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "secret-key")

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> list[dict[str, Any]]:
        del endpoint, params, api_key, timeout
        return [
            _row(
                student_name="강지연",
                measured_at="2026-03-07",
                session_id="session-old",
                record_value=210.0,
                variable_key="takeoff_angle",
                variable_value=21.5,
            ),
            _row(
                student_name="강지연",
                measured_at="2026-03-31",
                session_id="session-new",
                record_value=220.0,
                variable_key="horizontal_velocity",
                variable_name="앞으로 나가는 속도",
                variable_value=4.2,
                unit="m/s",
            ),
        ]

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)

    result = build_max_analysis_variables_response({"student_name": "강지연", "sport": "제멀"})

    assert result["latest_record"] == {
        "student_name": "강지연",
        "academy_name": "맥스체대입시_일산 교육원",
        "sport": "SLJ",
        "measured_at": "2026-03-31",
        "record_value": 220.0,
        "record_unit": "cm",
        "session_id": "session-new",
    }
    assert list(result).index("latest_record") < list(result).index("records")
    assert list(result).index("llm_context") < list(result).index("session_summaries")
    assert list(result).index("session_summaries") < list(result).index("records")
    assert result["llm_context"]["latest_record"] == "2026-03-31 / 220.0cm"
    assert result["session_summaries"][0]["session_id"] == "session-new"
    assert result["session_summaries"][0]["variables"] == [
        {
            "variable_key": "horizontal_velocity",
            "variable_name": "앞으로 나가는 속도",
            "value": 4.2,
            "unit": "m/s",
            "phase": "takeoff",
        }
    ]


def test_collect_all_pages_until_short_page(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "secret-key")
    offsets: list[int] = []

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> list[dict[str, Any]]:
        del endpoint, api_key, timeout
        offsets.append(int(params["offset"]))
        if params["offset"] == 0:
            return [_row(variable_key="ankle_angle"), _row(variable_key="knee_angle")]
        return [_row(variable_key="hip_angle")]

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)

    result = build_max_analysis_variables_response({"limit": 2, "collect_all_pages": True, "max_pages": 5})

    assert result["ok"] is True
    assert offsets == [0, 2]
    assert result["pagination"]["pages_fetched"] == 2
    assert result["pagination"]["exhausted"] is True
    assert result["record_count"] == 3
    assert {item["variable_key"] for item in result["variables"]} == {"ankle_angle", "knee_angle", "hip_angle"}


def test_http_auth_failure_returns_korean_plain_error(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "secret-key")

    def fake_get_json(endpoint: str, *, params: dict[str, Any], api_key: str, timeout: int) -> list[dict[str, Any]]:
        del endpoint, params, api_key, timeout
        raise urllib.error.HTTPError("https://example.test", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(max_analysis_api, "_http_get_json", fake_get_json)

    result = build_max_analysis_variables_response({})

    assert result["ok"] is False
    assert result["error_code"] == "auth_failed"
    rendered = json.dumps(result, ensure_ascii=False)
    assert "API 인증에 실패했다" in rendered
    assert "401" not in rendered
    assert "Unauthorized" not in rendered


def test_tool_handler_returns_json_contract(monkeypatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "secret-key")
    monkeypatch.setattr(max_analysis_api, "_http_get_json", lambda *_args, **_kwargs: [_row()])

    result = json.loads(max_analysis_variables_tool_handler({"academy_name": "일산"}))

    assert result["ok"] is True
    assert result["auth"] == {"env_var": API_KEY_ENV, "configured": True}
