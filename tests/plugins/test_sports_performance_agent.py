"""Tests for sports performance coach and reviewer plugin."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from plugins import sports_performance
from plugins.sports_performance.feedback_tool import feedback_tool_handler, make_feedback_tool_handler
from plugins.sports_performance.motion_analysis import (
    build_video_analysis,
    provider_status_payload,
    video_analysis_tool_handler,
)
from plugins.sports_performance.result_reviewer import review_tool_result


class _Ctx:
    def __init__(self) -> None:
        self.tools: list[str] = []
        self.hooks: list[str] = []
        self.tasks: list[dict[str, Any]] = []

    def register_tool(self, *, name: str, **_: Any) -> None:
        self.tools.append(name)

    def register_hook(self, name: str, *_args: Any, **_kwargs: Any) -> None:
        self.hooks.append(name)

    def register_auxiliary_task(self, key: str, **kwargs: Any) -> None:
        self.tasks.append({"key": key, **kwargs})


class _FakeLlm:
    def __init__(self, parsed: dict[str, Any]) -> None:
        self.parsed = parsed
        self.calls: list[dict[str, Any]] = []

    def complete_structured(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(parsed=self.parsed)


def _plugin_yaml_tools() -> list[str]:
    lines = Path("plugins/sports_performance/plugin.yaml").read_text(encoding="utf-8").splitlines()
    tools: list[str] = []
    in_tools = False
    for line in lines:
        stripped = line.strip()
        if stripped == "tools:":
            in_tools = True
            continue
        if in_tools and line and not line.startswith(" ") and not line.startswith("-"):
            break
        if in_tools and stripped.startswith("- "):
            tools.append(stripped[2:])
    return tools


def test_sports_performance_plugin_registers_tools_review_hook_and_agents() -> None:
    ctx = _Ctx()

    sports_performance.register(ctx)

    assert _plugin_yaml_tools() == ctx.tools
    assert ctx.tools == [
        "sports_motion_schema",
        "sports_pe_brain_evidence",
        "sports_motion_feedback",
        "sports_video_analyze",
    ]
    assert "transform_tool_result" in ctx.hooks
    task_keys = {task["key"] for task in ctx.tasks}
    assert {"sports_performance_coach", "sports_performance_reviewer"} <= task_keys


def test_sports_performance_plugin_loads_as_bundled_backend(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    from miho_cli.plugins import PluginManager, get_plugin_auxiliary_tasks

    manager = PluginManager()
    manager.discover_and_load()

    loaded = manager._plugins["sports_performance"]
    keys = {task["key"] for task in get_plugin_auxiliary_tasks()}
    assert loaded.enabled
    assert loaded.error is None
    assert {"sports_performance_coach", "sports_performance_reviewer"} <= keys


def test_motion_feedback_accepts_five_core_exercises() -> None:
    exercises = [
        "standing_long_jump",
        "medicine_ball_throw",
        "shuttle_run",
        "back_strength",
        "sit_and_reach",
    ]

    for exercise in exercises:
        result = json.loads(
            feedback_tool_handler(
                {
                    "student_name": "홍예지",
                    "exercise": exercise,
                    "metrics": {"launch_angle": 24, "knee_angle": 128, "ankle_angle": 72},
                    "records": {"latest": 217, "unit": "cm"},
                }
            )
        )

        assert result["ok"] is True
        assert result["student_name"] == "홍예지"
        assert result["exercise"]["key"] == exercise
        assert result["evidence_status"] == "pending_source_pack"
        assert result["coach_output"]["bottlenecks"]
        assert result["coach_output"]["drills"]
        assert "논문팩" in result["evidence_note"]


def test_motion_schema_does_not_require_student_name() -> None:
    result = json.loads(feedback_tool_handler({"exercise": "제멀", "metrics": {"발사각": 22}}))
    schema = json.loads(sports_performance.schema_tool_handler({}))

    assert schema["required"] == ["exercise", "metrics"]
    assert "student_name" in schema["optional"]
    assert result["ok"] is True
    assert result["student_name"] == "학생"


def test_sports_video_analyze_reports_provider_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.sports_performance.motion_analysis._is_module_available",
        lambda name: name in {"Sports2D", "rtmlib", "cv2"},
    )
    monkeypatch.setattr(
        "plugins.sports_performance.motion_analysis._find_executable",
        lambda name: "/fake/bin/sports2d" if name == "sports2d" else None,
    )

    status = provider_status_payload()

    sports2d = status["providers"]["sports2d_rtmpose_2d"]
    assert sports2d["available"] is True
    assert sports2d["cost"] == "free_open_source"
    assert "단일카메라" in " ".join(status["single_camera_limitations"])


def test_sports_video_analyze_dry_run_builds_sports2d_command(tmp_path, monkeypatch) -> None:
    video = tmp_path / "jump.mp4"
    video.write_bytes(b"fake video bytes")
    monkeypatch.setattr(
        "plugins.sports_performance.motion_analysis._is_module_available",
        lambda name: name in {"Sports2D", "rtmlib", "cv2"},
    )
    monkeypatch.setattr(
        "plugins.sports_performance.motion_analysis._find_executable",
        lambda name: "/fake/bin/sports2d" if name == "sports2d" else None,
    )

    result = build_video_analysis(
        {
            "student_name": "홍예지",
            "exercise": "제멀",
            "video_path": str(video),
            "provider": "auto",
            "camera_view": "side",
            "execute": False,
        }
    )

    assert result["ok"] is True
    assert result["analysis_status"] == "ready_to_execute"
    assert result["provider"]["key"] == "sports2d_rtmpose_2d"
    assert result["exercise"]["key"] == "standing_long_jump"
    assert "--video_input" in result["command_preview"]
    assert result["command_preview"][
        result["command_preview"].index("--person_ordering_method") + 1
    ] == "highest_likelihood"
    assert result["command_preview"][result["command_preview"].index("--nb_persons_to_detect") + 1] == "1"
    assert "not_3d_verified" in result["measurement_contract"]["warnings"]


def test_sports_video_analyze_missing_video_returns_korean_error() -> None:
    result = json.loads(
        video_analysis_tool_handler(
            {
                "student_name": "홍예지",
                "exercise": "제멀",
                "video_path": "/tmp/없는영상.mp4",
                "provider": "auto",
            }
        )
    )

    assert result["ok"] is False
    assert "영상 파일" in " ".join(result["errors"])
    assert "Traceback" not in json.dumps(result, ensure_ascii=False)


def test_sports_video_analyze_does_not_claim_direct_rtmpose_execution(tmp_path, monkeypatch) -> None:
    video = tmp_path / "jump.mp4"
    video.write_bytes(b"fake video bytes")
    monkeypatch.setattr(
        "plugins.sports_performance.motion_analysis._is_module_available",
        lambda name: name in {"rtmlib", "cv2"},
    )
    monkeypatch.setattr("plugins.sports_performance.motion_analysis._find_executable", lambda name: None)

    result = build_video_analysis(
        {
            "student_name": "홍예지",
            "exercise": "제멀",
            "video_path": str(video),
            "provider": "rtmpose",
        }
    )

    assert result["ok"] is False
    assert "직접 실행" in " ".join(result["errors"])


def test_sports_video_analyze_execute_timeout_returns_korean_error(tmp_path, monkeypatch) -> None:
    video = tmp_path / "jump.mp4"
    video.write_bytes(b"fake video bytes")
    monkeypatch.setattr(
        "plugins.sports_performance.motion_analysis._is_module_available",
        lambda name: name in {"Sports2D", "rtmlib", "cv2"},
    )
    monkeypatch.setattr(
        "plugins.sports_performance.motion_analysis._find_executable",
        lambda name: "/fake/bin/sports2d" if name == "sports2d" else None,
    )

    def _timeout_runner(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=["sports2d"], timeout=1)

    result = build_video_analysis(
        {
            "student_name": "홍예지",
            "exercise": "제멀",
            "video_path": str(video),
            "execute": True,
            "timeout_seconds": 30,
        },
        runner=_timeout_runner,
    )

    assert result["ok"] is False
    assert result["analysis_status"] == "failed"
    assert "시간" in " ".join(result["errors"])
    assert "Traceback" not in json.dumps(result, ensure_ascii=False)


def test_sports_video_analyze_execute_failure_hides_raw_stderr(tmp_path, monkeypatch) -> None:
    video = tmp_path / "jump.mp4"
    video.write_bytes(b"fake video bytes")
    monkeypatch.setattr(
        "plugins.sports_performance.motion_analysis._is_module_available",
        lambda name: name in {"Sports2D", "rtmlib", "cv2"},
    )
    monkeypatch.setattr(
        "plugins.sports_performance.motion_analysis._find_executable",
        lambda name: "/fake/bin/sports2d" if name == "sports2d" else None,
    )

    def _failed_runner(*_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["sports2d"],
            returncode=2,
            stdout="Traceback with /Users/etlab/private/video.mp4",
            stderr="Traceback with /Users/etlab/private/video.mp4",
        )

    result = build_video_analysis(
        {
            "student_name": "홍예지",
            "exercise": "제멀",
            "video_path": str(video),
            "execute": True,
        },
        runner=_failed_runner,
    )

    rendered = json.dumps(result, ensure_ascii=False)
    assert result["ok"] is False
    assert "Traceback" not in rendered
    assert "/Users/etlab/private" not in rendered
    assert result["diagnostics"]["returncode"] == 2


def test_sports_video_analyze_output_dir_file_error_is_korean(tmp_path, monkeypatch) -> None:
    video = tmp_path / "jump.mp4"
    video.write_bytes(b"fake video bytes")
    output_file = tmp_path / "not_a_dir"
    output_file.write_text("already a file", encoding="utf-8")
    monkeypatch.setattr(
        "plugins.sports_performance.motion_analysis._is_module_available",
        lambda name: name in {"Sports2D", "rtmlib", "cv2"},
    )
    monkeypatch.setattr(
        "plugins.sports_performance.motion_analysis._find_executable",
        lambda name: "/fake/bin/sports2d" if name == "sports2d" else None,
    )

    result = build_video_analysis(
        {
            "student_name": "홍예지",
            "exercise": "제멀",
            "video_path": str(video),
            "output_dir": str(output_file),
            "execute": True,
        }
    )

    assert result["ok"] is False
    assert "결과 폴더" in " ".join(result["errors"])


def test_motion_feedback_maps_korean_alias_and_safety_flags() -> None:
    result = json.loads(
        feedback_tool_handler(
            {
                "student_name": "홍예지",
                "exercise": "제멀",
                "metrics": {"발사각": 22, "무릎각도": 126, "착지안정성": "불안정"},
                "pain_flags": ["무릎 통증"],
            }
        )
    )

    assert result["exercise"]["key"] == "standing_long_jump"
    assert result["safety"]["status"] == "needs_human_check"
    assert any("통증" in item for item in result["coach_output"]["avoid"])
    assert "launch_angle" in result["normalized_metrics"]


def test_motion_feedback_uses_coach_agent_when_llm_is_available() -> None:
    fake = _FakeLlm(
        {
            "summary": "발사각과 착지 안정성을 우선 교정한다.",
            "bottlenecks": ["발사각이 낮아 체공 시간이 짧다."],
            "technical_cues": ["팔스윙을 먼저 열고 고관절 신전을 끝까지 만든다."],
            "drills": ["암스윙 브로드점프 4x4"],
            "one_week_plan": ["기술 드릴 2회, 재측정 1회"],
            "avoid": ["무릎 통증이 있으면 반복 점프를 중단한다."],
        }
    )
    handler = make_feedback_tool_handler(fake)

    result = json.loads(
        handler(
            {
                "student_name": "홍예지",
                "exercise": "제멀",
                "metrics": {"발사각": 22, "무릎각도": 126},
                "pain_flags": ["무릎 통증"],
            }
        )
    )

    assert result["coach_agent"]["mode"] == "llm_subagent"
    assert result["coach_output"]["summary"] == "발사각과 착지 안정성을 우선 교정한다."
    assert fake.calls[0]["purpose"] == "sports_performance_coach"


def test_sports_reviewer_retries_pending_evidence_and_blocks_missing_sections() -> None:
    raw = feedback_tool_handler(
        {
            "student_name": "홍예지",
            "exercise": "왕복달리기",
            "metrics": {"turn_angle": 68, "contact_time": 0.42},
        }
    )

    reviewed = json.loads(
        review_tool_result(tool_name="sports_motion_feedback", args={}, result=raw) or raw
    )

    assert reviewed["reviewer"]["status"] == "retry_needed"
    assert reviewed["reviewer"]["name"] == "sports_performance_reviewer"
    assert reviewed["reviewer"]["retry_tools"] == ["sports_pe_brain_evidence", "sports_motion_feedback"]
    assert reviewed["next_action"] == "retry_required"

    blocked = json.loads(
        review_tool_result(
            tool_name="sports_motion_feedback",
            args={},
            result=json.dumps({"ok": True, "coach_output": {"drills": []}}, ensure_ascii=False),
        )
        or "{}"
    )

    assert blocked["ok"] is False
    assert blocked["reviewer"]["status"] == "blocked"
    assert "학생명" in " ".join(blocked["errors"])


def test_sports_reviewer_uses_agent_after_hard_gate_passes(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.sports_performance.pe_brain_evidence.load_pe_brain_evidence_packs",
        lambda: [
            {
                "id": "pe_brain:99",
                "source": "pe_brain",
                "paper_id": "99",
                "title": "Shuttle run change of direction study",
                "category": "physical",
                "evidence_depth": "summary_only",
                "domain_tags": ["shuttle_run"],
                "exercise_keys": ["shuttle_run"],
                "quality_status": "accepted",
            }
        ],
    )
    raw = feedback_tool_handler(
        {
            "student_name": "홍예지",
            "exercise": "왕복달리기",
            "metrics": {"turn_angle": 68, "contact_time": 0.42},
            "evidence_refs": ["pe_brain:99"],
        }
    )
    fake = _FakeLlm({"status": "pass", "errors": [], "checked": ["안전", "근거", "종목 적합성"]})

    reviewed = json.loads(
        review_tool_result(tool_name="sports_motion_feedback", args={}, result=raw, llm=fake) or raw
    )

    assert reviewed["reviewer"]["mode"] == "llm_subagent"
    assert reviewed["reviewer"]["checked"] == ["안전", "근거", "종목 적합성"]
    assert fake.calls[0]["purpose"] == "sports_performance_reviewer"
