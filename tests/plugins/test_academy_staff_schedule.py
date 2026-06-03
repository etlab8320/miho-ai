"""Tests for Peak instructor schedule lookup."""

from __future__ import annotations

import json
from datetime import date

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from miho_cli.plugins import PluginContext, PluginManager, PluginManifest
from plugins.academy_ops import _academy_command, _capture_gateway_context, register
from plugins.academy_ops.auth_store import AcademyBinding, save_binding
from plugins.academy_ops.academy_query_tools import _capability_status_tool_handler
from plugins.academy_ops.codex_model_policy import session_model
from plugins.academy_ops.quick_router import classify_quick_operation, quick_command_for
from plugins.academy_ops.staff_schedule_tool import _staff_schedule_day_tool_handler


def _payload(raw: str) -> dict:
    return json.loads(raw)


def test_staff_schedule_tool_reads_peak_assignments_without_sensitive_fields() -> None:
    class StaffScheduleClient:
        def get_peak_assignments(self, day: date, *, time_slot: str = "") -> dict:
            assert day == date(2026, 5, 27)
            assert time_slot == ""
            return {
                "success": True,
                "date": "2026-05-27",
                "slots": {
                    "evening": {
                        "waitingInstructors": [
                            {"id": 1, "name": "박성준", "phone": "010-1111-2222", "isOwner": False},
                            {"id": 2, "name": "오철민", "salary_type": "hourly", "isOwner": False},
                        ],
                        "classes": [],
                    }
                },
            }

    result = _payload(
        _staff_schedule_day_tool_handler(
            {"date": "2026-05-27"},
            client=StaffScheduleClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "staff.schedule_day"
    assert result["summary"]["scheduled"] == 2
    assert [row["name"] for row in result["instructors"]] == ["박성준", "오철민"]
    assert "저녁반: 박성준, 오철민" in result["message"]
    dumped = json.dumps(result, ensure_ascii=False)
    assert "010-" not in dumped
    assert "salary_type" not in dumped


def test_staff_schedule_tool_excludes_owner_for_instructor_question_by_default() -> None:
    class StaffScheduleClient:
        def get_peak_assignments(self, day: date, *, time_slot: str = "") -> dict:
            return {
                "date": day.isoformat(),
                "slots": {
                    "morning": {
                        "waitingInstructors": [
                            {"id": 1, "name": "정으뜸", "isOwner": True},
                            {"id": 2, "name": "박성준", "isOwner": False},
                        ]
                    }
                },
            }

    result = _payload(
        _staff_schedule_day_tool_handler(
            {"date": "2026-05-27"},
            client=StaffScheduleClient(),
        )
    )

    assert [row["name"] for row in result["instructors"]] == ["박성준"]
    assert "정으뜸" not in result["message"]


def test_staff_schedule_tool_includes_class_assigned_instructors() -> None:
    class StaffScheduleClient:
        def get_peak_assignments(self, day: date, *, time_slot: str = "") -> dict:
            return {
                "date": day.isoformat(),
                "slots": {
                    "evening": {
                        "waitingInstructors": [{"id": 1, "name": "정으뜸", "isOwner": True}],
                        "classes": [
                            {
                                "classNumber": 1,
                                "instructors": [{"id": 2, "name": "오철민", "isOwner": False}],
                            },
                            {
                                "classNumber": 2,
                                "instructors": [{"id": 3, "name": "정의솔", "isOwner": False}],
                            },
                        ],
                    }
                },
            }

    result = _payload(
        _staff_schedule_day_tool_handler(
            {"date": "2026-06-03"},
            client=StaffScheduleClient(),
        )
    )

    assert [row["name"] for row in result["instructors"]] == ["오철민", "정의솔"]
    assert "저녁반: 오철민, 정의솔" in result["message"]
    assert "정으뜸" not in result["message"]


def test_staff_schedule_tool_can_include_owner_when_request_says_so() -> None:
    class StaffScheduleClient:
        def get_peak_assignments(self, day: date, *, time_slot: str = "") -> dict:
            return {
                "date": day.isoformat(),
                "slots": {
                    "morning": {
                        "waitingInstructors": [
                            {"id": 1, "name": "정으뜸", "isOwner": True},
                            {"id": 2, "name": "박성준", "isOwner": False},
                        ]
                    }
                },
            }

    result = _payload(
        _staff_schedule_day_tool_handler(
            {"date": "2026-05-27", "include_owner": True},
            client=StaffScheduleClient(),
        )
    )

    assert [row["name"] for row in result["instructors"]] == ["정으뜸", "박성준"]
    assert "오전반: 정으뜸, 박성준" in result["message"]


def test_future_staff_work_question_is_not_quick_routed() -> None:
    request = "내일 출근 해야할 강사 누구야?"

    assert classify_quick_operation(request) == ""
    assert quick_command_for(request) == ""


def test_capability_status_recommends_staff_schedule_tool() -> None:
    result = _payload(_capability_status_tool_handler({"operation_key": "staff.schedule_day"}))

    assert result["ok"] is True
    assert result["operation_key"] == "staff.schedule_day"
    assert result["can_execute_now"] is True
    assert result["recommended_tool"] == "academy_staff_schedule_day"


def test_past_staff_work_question_is_not_quick_routed() -> None:
    request = "어제 출근한 강사 목록좀 줘"

    assert classify_quick_operation(request) == ""
    assert quick_command_for(request) == ""


def test_gateway_context_allows_and_routes_bound_academy_session(monkeypatch, tmp_path) -> None:
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
    event = MessageEvent(
        text="내일 출근 해야할 강사 누구야?",
        source=SessionSource(
            platform=Platform.DISCORD,
            user_id="discord-user-1",
            chat_id="channel-1",
            guild_id="guild-1",
        ),
    )

    class Gateway:
        def __init__(self) -> None:
            self._session_model_overrides = {}

        def _session_key_for_source(self, source):
            return source.chat_id

        def _evict_cached_agent(self, session_key):
            return None

    gateway = Gateway()
    result = _capture_gateway_context(event, gateway=gateway)

    assert result["action"] == "allow"
    assert gateway._session_model_overrides["channel-1"]["model"] == session_model()


def test_academy_quick_staff_schedule_is_disabled() -> None:
    output = _academy_command("quick staff.schedule_day 내일 출근 해야할 강사 누구야")

    assert "빠른 문장 가로채기는 꺼져 있어" in output


def test_plugin_registers_staff_schedule_tool() -> None:
    manager = PluginManager()
    manifest = PluginManifest(name="academy_ops", source="bundled", key="academy_ops")
    ctx = PluginContext(manifest, manager)

    register(ctx)

    assert "academy_staff_schedule_day" in manager._plugin_tool_names
