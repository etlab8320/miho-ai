"""Tests for Peak class assignment lookup tools."""

from __future__ import annotations

from datetime import date
import json

from miho_cli.plugins import PluginContext, PluginManager, PluginManifest
from plugins.academy_ops import register
from plugins.academy_ops.academy_query_tools import _capability_status_tool_handler
from plugins.academy_ops.assignment_tool import _assignment_by_date_tool_handler


def _payload(raw: str) -> dict:
    return json.loads(raw)


class AssignmentClient:
    def get_peak_assignments(self, day: date, *, time_slot: str = "") -> dict:
        assert day == date(2026, 5, 25)
        assert time_slot == "evening"
        return {
            "date": "2026-05-25",
            "slots": {
                "evening": {
                    "waitingStudents": [
                        {
                            "id": 100,
                            "student_id": 501,
                            "student_name": "김태양",
                            "phone": "010-1111-2222",
                            "attendance_status": "absent",
                            "absence_reason": "개인사정",
                        }
                    ],
                    "classes": [
                        {
                            "class_num": 1,
                            "instructors": [{"id": 1, "name": "박성준", "isMain": True}],
                            "students": [
                                {
                                    "id": 10,
                                    "student_id": 601,
                                    "student_name": "박지안",
                                    "school": "행신고",
                                    "grade": "고3",
                                    "parent_phone": "010-2222-3333",
                                    "attendance_status": "present",
                                }
                            ],
                        }
                    ],
                }
            },
        }


def test_assignment_by_date_tool_returns_safe_class_assignment() -> None:
    result = _payload(
        _assignment_by_date_tool_handler(
            {"date": "2026-05-25", "time_slot": "evening"},
            client=AssignmentClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "assignment.by_date"
    assert result["summary"] == {"slots": 1, "classes": 1, "assigned_students": 1, "waiting_students": 1}
    evening = result["slots"]["evening"]
    assert evening["classes"][0]["instructors"][0]["name"] == "박성준"
    assert evening["classes"][0]["students"][0]["student_name"] == "박지안"
    assert evening["waiting_students"][0]["student_name"] == "김태양"
    assert "1반 / 박성준 (1명): 박지안" in result["message"]
    assert "미배정 (1명): 김태양" in result["message"]
    dumped = json.dumps(result, ensure_ascii=False)
    assert "010-" not in dumped


def test_assignment_tool_requires_llm_resolved_date() -> None:
    result = _payload(_assignment_by_date_tool_handler({"request": "어제 반배치"}, client=AssignmentClient()))

    assert result["ok"] is False
    assert "YYYY-MM-DD" in result["message"]


def test_capability_status_recommends_assignment_tool() -> None:
    result = _payload(_capability_status_tool_handler({"operation_key": "assignment.by_date"}))

    assert result["ok"] is True
    assert result["operation_key"] == "assignment.by_date"
    assert result["can_execute_now"] is True
    assert result["recommended_tool"] == "academy_assignment_by_date"


def test_plugin_registers_assignment_tool() -> None:
    manager = PluginManager()
    manifest = PluginManifest(name="academy_ops", source="bundled", key="academy_ops")
    ctx = PluginContext(manifest, manager)

    register(ctx)

    assert "academy_assignment_by_date" in manager._plugin_tool_names
