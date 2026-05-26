"""Tests for Peak daily plan lookup and fast routing."""

from __future__ import annotations

import json
from datetime import date

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.academy_ops import _academy_command, _capture_gateway_context
from plugins.academy_ops.academy_query_tools import _plan_by_date_tool_handler
from plugins.academy_ops.auth_store import AcademyBinding, save_binding
from plugins.academy_ops.plan_lookup import extract_trainer_query, plan_lookup_for_day
from plugins.academy_ops.quick_router import classify_quick_operation, quick_command_for


class PlanClient:
    def get_peak_plans(self, day: date, *, time_slot: str = "") -> dict:
        assert day == date(2026, 5, 25)
        assert time_slot == ""
        return {
            "success": True,
            "date": "2026-05-25",
            "plans": [
                {
                    "id": 330,
                    "date": "2026-05-25",
                    "time_slot": "evening",
                    "instructor_id": 1,
                    "instructor_name": "박성준",
                    "updated_at": "2026-05-25 20:50:59",
                    "exercises": [
                        {"exercise_id": 344, "name": "20m왕복달리기", "note": "측정"},
                        {"exercise_id": 230, "name": "cc스쿼트", "note": ""},
                    ],
                    "completed_exercises": [344],
                },
                {
                    "id": 331,
                    "date": "2026-05-25",
                    "time_slot": "evening",
                    "instructor_name": "오철민",
                    "exercises": [],
                    "completed_exercises": [],
                },
            ],
        }


def test_plan_lookup_filters_trainer_and_marks_completion() -> None:
    result = plan_lookup_for_day(PlanClient(), date(2026, 5, 25), trainer_query="박성준")

    assert result["summary"] == {"plans": 1, "exercises": 2, "completed": 1}
    assert result["plans"][0]["instructor_name"] == "박성준"
    assert result["plans"][0]["exercises"][0]["completed"] is True
    assert result["plans"][0]["exercises"][1]["completed"] is False


def test_plan_tool_reads_request_date_and_trainer_without_sensitive_fields() -> None:
    result = json.loads(
        _plan_by_date_tool_handler(
            {"request": "2026-05-25 박성준 운동계획서좀 줘"},
            client=PlanClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "plan.by_date"
    assert result["date"] == "2026-05-25"
    assert result["trainer_query"] == "박성준"
    assert result["plans"][0]["completed_count"] == 1
    dumped = json.dumps(result, ensure_ascii=False)
    assert "010-" not in dumped


def test_quick_router_rewrites_workout_plan_request() -> None:
    request = "2026-05-25 박성준 운동계획서좀 줘"

    assert extract_trainer_query(request) == "박성준"
    assert classify_quick_operation(request) == "plan.by_date"
    assert quick_command_for(request) == "/academy quick plan.by_date 2026-05-25 박성준 운동계획서좀 줘"


def test_gateway_context_rewrites_bound_plan_request(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    save_binding(
        AcademyBinding(
            discord_user_id="discord-user-1",
            user_id="1",
            email="owner@example.com",
            name="원장",
            role="owner",
            academy_id="2",
            academy_name="학원",
            token_ciphertext="ciphertext",
            created_at=1,
            updated_at=1,
        )
    )

    result = _capture_gateway_context(
        MessageEvent(
            text="2026-05-25 박성준 운동계획서좀 줘",
            source=SessionSource(
                platform=Platform.DISCORD,
                user_id="discord-user-1",
                chat_id="channel-1",
                guild_id="guild-1",
            ),
        )
    )

    assert result == {"action": "rewrite", "text": "/academy quick plan.by_date 2026-05-25 박성준 운동계획서좀 줘"}


def test_academy_quick_plan_formats_tool_payload(monkeypatch) -> None:
    def fake_plan_tool(args):
        assert args["date"] == "2026-05-25"
        return json.dumps(
            {
                "ok": True,
                "date": "2026-05-25",
                "plans": [
                    {
                        "id": 330,
                        "time_slot": "evening",
                        "instructor_name": "박성준",
                        "completed_count": 1,
                        "exercises": [
                            {"name": "20m왕복달리기", "note": "측정", "completed": True},
                            {"name": "cc스쿼트", "note": "", "completed": False},
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("plugins.academy_ops._plan_by_date_tool_handler", fake_plan_tool)

    output = _academy_command("quick plan.by_date 2026-05-25 박성준 운동계획서좀 줘")

    assert "2026-05-25 박성준 강사 운동계획서" in output
    assert "완료: 1/2" in output
    assert "- cc스쿼트 (미완료)" in output
