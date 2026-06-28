"""Tests for the sports performance HTML/PDF report shell."""

from __future__ import annotations

import json
import re
from pathlib import Path

from plugins.sports_performance.report_html import (
    build_sports_report_html_payload,
    render_sports_report_html,
    sports_report_html_tool_handler,
)


def test_sports_report_html_renders_distinct_a4_shell_with_logo_and_training() -> None:
    html = render_sports_report_html(
        {
            "exercise": "제멀",
            "mode": "template_preview",
            "student": {"name": "권동욱", "gender": "남", "academy": "일산"},
            "record": {"current": "245 cm", "previous": "238 cm", "change": "+7 cm"},
        }
    )

    assert html.startswith("<!doctype html>")
    assert "sport-report" in html
    assert "MAX PERFORMANCE LAB" in html
    assert "data:image/png;base64," in html
    assert "권동욱" in html
    assert "전국 성별 상위 1%" in html
    assert "이번 학생 우선 보강운동 3개" in html
    assert "왜 이 운동인가" in html
    visible_html = re.sub(r"data:[^\"']+", "", html)
    assert "빠른 반전 CMJ" not in visible_html
    assert "takeoff_transition_time" not in visible_html
    assert "앉았다 밀고 나가기까지 걸린 시간" in html
    assert "앉은 뒤 점프를 시작하기까지 늦는지 본다." in html
    assert "4주" in html
    assert "주 3회" in html
    assert "word-break: keep-all" in html
    assert "overflow-wrap: anywhere" in html
    assert "table-layout: fixed" in html
    assert "GoyangDeogyang" in html
    assert "oklch(" in html
    assert "학생부종합" not in html
    assert "수시 실기전형" not in html
    assert "shadcn/ui" not in html
    assert "github.com/shadcn-ui" not in html
    assert "실제 API 조회값 연결 시 표시" not in html
    assert "Evidence & Review" not in html
    assert "근거와 후검증 체크" not in html


def test_sports_report_exercise_library_uses_custom_step_layout_without_evidence_page() -> None:
    html = render_sports_report_html(
        {
            "exercise": "제멀",
            "student": {"name": "오윤지", "gender": "여", "academy": "일산"},
            "record": {"current": "153 cm", "previous": "196 cm", "change": "-43 cm"},
            "variables": [
                {
                    "variable_key": "arm_backswing_angle",
                    "variable_value": 98.1,
                    "elite_1pct": "56.86 °",
                    "unit": "°",
                    "measured_at": "2026-06-29",
                },
                {
                    "variable_key": "arm_swing_peak_velocity",
                    "variable_value": 754.04,
                    "elite_1pct": "914.20 °/s",
                    "unit": "°/s",
                    "measured_at": "2026-06-29",
                },
            ],
        }
    )

    assert "method-list" in html
    assert "method-step" in html
    assert "step-index" in html
    assert '<ol class="weekly-list">' not in html
    assert "추가 보강운동 라이브러리" in html
    assert "운동분석 리포트 · 로컬 종목 논문팩 우선" not in html
    assert "05 / 05" in html


def test_sports_report_main_prescription_uses_plain_action_copy() -> None:
    html = render_sports_report_html(
        {
            "exercise": "제멀",
            "student": {"name": "오윤지", "gender": "여", "academy": "일산"},
            "record": {"current": "153 cm", "previous": "196 cm", "change": "-43 cm"},
            "variables": [
                {
                    "variable_key": "com_foot_distance",
                    "variable_value": 30.0,
                    "elite_1pct": "56.0 cm",
                    "unit": "cm",
                    "measured_at": "2026-06-29",
                },
                {
                    "variable_key": "flight_hip_min_angle",
                    "variable_value": 25.82,
                    "elite_1pct": "44.91 °",
                    "unit": "°",
                    "measured_at": "2026-06-29",
                },
            ],
        }
    )

    assert "바로 시키는 법" in html
    assert "코치 멘트" in html
    assert "보조 포인트 처방" in html
    assert "각도·각속도·타이밍 보정용 포인트 처방" in html
    assert "메인 3개 포인트 처방 집중" in html
    assert "중복 운동을 제외" in html
    assert "추가 부하 없음" in html
    assert "착지 감속 스플릿 스쿼트와 수건 햄스트링 컬" not in html
    assert "이센트릭 스플릿 스쿼트와 햄스트링 컬" not in html
    assert "고중량" not in html


def test_sports_report_main_prescription_prioritizes_selected_exercises_not_generic_drills() -> None:
    html = render_sports_report_html(
        {
            "exercise": "제멀",
            "student": {"name": "오윤지", "gender": "여", "academy": "일산"},
            "record": {"current": "153 cm", "previous": "196 cm", "change": "-43 cm"},
            "variables": [
                {
                    "variable_key": "arm_backswing_angle",
                    "variable_value": 98.1,
                    "elite_1pct": "56.86 °",
                    "unit": "°",
                    "measured_at": "2026-06-29",
                },
                {
                    "variable_key": "arm_swing_peak_velocity",
                    "variable_value": 754.04,
                    "elite_1pct": "914.20 °/s",
                    "unit": "°/s",
                    "measured_at": "2026-06-29",
                },
                {
                    "variable_key": "knee_peak_angular_velocity",
                    "variable_value": 616.38,
                    "elite_1pct": "719.77 °/s",
                    "unit": "°/s",
                    "measured_at": "2026-06-29",
                },
            ],
        }
    )

    assert "이번 학생 우선 보강운동 3개" in html
    assert "왜 이 운동인가" in html
    assert "운동 방법" in html
    assert "영상 ·" in html
    assert "메디신볼 전방 스윙 점프" in html
    assert "메디신볼 제멀" not in html
    assert "팔 흔드는 타이밍 맞추기" not in html


def test_sports_report_html_escapes_user_content() -> None:
    html = render_sports_report_html(
        {
            "exercise": "제멀",
            "mode": "template_preview",
            "student": {"name": "<script>alert(1)</script>", "academy": "일산"},
        }
    )

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_sports_report_payload_links_variables_to_training_effects() -> None:
    report = build_sports_report_html_payload({"exercise": "제멀", "mode": "template_preview"})
    variable_keys = {
        variable["key"]
        for group in report["variable_groups"]
        for variable in group["variables"]
    }
    effect_keys = {
        effect["variable_key"]
        for block in report["training_program"]["exercise_blocks"]
        for effect in block["expected_variable_effects"]
    }

    assert {"takeoff_angle", "horizontal_velocity", "takeoff_transition_time"} <= variable_keys
    assert {"takeoff_transition_time", "vertical_velocity", "horizontal_velocity"} <= effect_keys
    assert report["training_program"]["duration_weeks"] == 4
    assert report["training_program"]["sessions_per_week"] == 3
    assert report["training_program"]["exercise_blocks"][0]["title"] == "앉았다 바로 점프하기"
    assert "앉았다 밀고 나가기까지 걸린 시간" in report["training_program"]["exercise_blocks"][0]["effect_summary"]
    assert report["design_reference"]["name"] == "MAX performance data report"


def test_sports_report_html_tool_rejects_unreviewed_placeholder_report(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    result = json.loads(sports_report_html_tool_handler({"exercise": "제멀", "student": {"name": "권동욱"}}))

    assert result["ok"] is False
    assert result["next_action"] == "run_sports_motion_report_package"
    assert "실제 변인" in " ".join(result["errors"])
    assert "html_path" not in result
    assert "MEDIA:" not in json.dumps(result, ensure_ascii=False)


def test_sports_report_html_tool_rejects_reviewed_variables_without_elite_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    result = json.loads(
        sports_report_html_tool_handler(
            {
                "exercise": "제멀",
                "student": {"name": "권동욱", "academy": "일산"},
                "record": {"current": "245 cm"},
                "variables": [
                    {
                        "variable_key": "takeoff_angle",
                        "variable_value": 22.4,
                        "unit": "deg",
                        "measured_at": "2026-06-28",
                    }
                ],
                "feedback": {"reviewer": {"status": "pass"}},
            }
        )
    )

    assert result["ok"] is False
    assert "상위 1%" in " ".join(result["errors"])
    assert "html_path" not in result
    assert "MEDIA:" not in json.dumps(result, ensure_ascii=False)
    assert "미연동" not in json.dumps(result, ensure_ascii=False)


def test_sports_report_html_tool_writes_html_only_with_reviewed_variables_and_elite_model(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    result = json.loads(
        sports_report_html_tool_handler(
            {
                "exercise": "제멀",
                "student": {"name": "권동욱", "academy": "일산"},
                "record": {"current": "245 cm", "percentile": "1% 모델 10세션"},
                "comparison": [
                    {"label": "전국 성별 상위 1%", "value": "남 1개 세션 모델", "note": "MAX API 전국 모델"},
                    {"label": "전국 성별 상위 5%", "value": "남 2개 세션 모델", "note": "MAX API 전국 모델"},
                ],
                "variables": [
                    {
                        "variable_key": "takeoff_angle",
                        "variable_value": 22.4,
                        "elite_1pct": 30.0,
                        "gap": "-7.60 deg",
                        "unit": "deg",
                        "status": "상위 1% 모델",
                        "measured_at": "2026-06-28",
                    }
                ],
                "feedback": {"reviewer": {"status": "pass"}},
            }
        )
    )
    html_path = Path(result["html_path"])

    assert result["ok"] is True
    assert result["template_key"] == "standing_long_jump_motion_report_v1"
    assert html_path.exists()
    assert html_path.parent.name == "sports_performance_reports"
    assert "media_tag" not in result
    html = html_path.read_text(encoding="utf-8")
    assert "권동욱" in html
    assert "22.40 deg" in html
    assert "전국 상위 1%" in html
    assert "30.00 deg" in html
    assert "측정 대기" not in html
    assert "대기" not in html
    assert "미연동" not in html
    assert "실제 API 조회값 연결 시 표시" not in html
    assert "github.com/shadcn-ui" not in html


def test_sports_report_html_prefers_latest_session_variables_from_max_analysis() -> None:
    report = build_sports_report_html_payload(
        {
            "exercise": "제멀",
            "max_analysis": {
                "records": [
                    {"variable_key": "takeoff_angle", "variable_value": 18.0, "unit": "deg", "measured_at": "2026-03-01"},
                ],
                "llm_context": {
                    "latest_session_variables": [
                        {
                            "variable_key": "takeoff_angle",
                            "variable_value": 23.5,
                            "unit": "deg",
                            "measured_at": "2026-03-31",
                        }
                    ]
                },
            },
            "record": {"current": "220 cm"},
        }
    )

    values = [
        variable["current"]
        for group in report["variable_groups"]
        for variable in group["variables"]
        if variable["key"] == "takeoff_angle"
    ]
    assert values == ["23.50 deg"]


def test_sports_report_html_tool_returns_korean_error_for_unsupported_exercise() -> None:
    result = json.loads(sports_report_html_tool_handler({"exercise": "좌전굴"}))

    assert result["ok"] is False
    assert "지원" in " ".join(result["errors"])
    assert "Traceback" not in json.dumps(result, ensure_ascii=False)


def test_sports_report_html_never_renders_unlinked_model_wording() -> None:
    html = render_sports_report_html(
        {
            "exercise": "제멀",
            "student": {"name": "오윤지", "gender": "여", "academy": "일산"},
            "record": {"current": "153 cm"},
            "variables": [
                {
                    "variable_key": "takeoff_angle",
                    "variable_value": 10.31,
                    "unit": "°",
                    "measured_at": "2026-06-29",
                }
            ],
            "feedback": {"reviewer": {"status": "pass"}},
        }
    )

    assert "미연동" not in html
    assert "전국 모델 재계산 필요" in html
