"""Governance integration checks for sports performance tools."""

from __future__ import annotations

import json

from plugins.governance_os.delivery_gate import evaluate_final_delivery
from plugins.governance_os.dispatcher import dispatch_request
from plugins.governance_os.registry import load_builtin_registry
from plugins.governance_os.result_transform import governance_transform_tool_result
from plugins.governance_os.review import evaluate_review_gate
from plugins.sports_performance.feedback_tool import make_feedback_tool_handler
from plugins.sports_performance.max_analysis_api import build_max_analysis_variables_response


def _max_api_payload() -> dict:
    return {
        "ok": True,
        "source": "max_analysis_variables_api",
        "endpoint": "https://example.invalid/analysis-variables",
        "auth": {"env_var": "MAX_ANALYSIS_VARIABLES_API_KEY", "configured": True},
        "scope": "all_academies",
        "query": {"student_name": "강지연", "sport": "slj", "limit": 1000, "offset": 0},
        "pagination": {
            "limit": 1000,
            "offset": 0,
            "collect_all_pages": True,
            "pages_fetched": 1,
            "next_offset": None,
            "exhausted": True,
        },
        "record_count": 1,
        "records": [
            {
                "student_name": "강지연",
                "sport": "slj",
                "variable_key": "takeoff_angle",
                "variable_name": "뛰어오르는 각도",
                "unit": "deg",
                "measured_at": "2026-06-27",
            }
        ],
        "summary": {"student_names": ["강지연"], "sports": ["slj"], "variable_key_count": 1},
        "variables": [{"variable_key": "takeoff_angle", "variable_name": "뛰어오르는 각도"}],
        "student_filter": {
            "active": True,
            "student_name": "강지연",
            "matched": True,
            "original_record_count": 1,
            "filtered_record_count": 1,
        },
        "warnings": [],
        "reviewer": {
            "name": "sports_max_api_reviewer",
            "status": "pass",
            "mode": "deterministic_api_integrity_gate",
            "checked": ["API 원천", "학생/종목/지표", "페이지/필터"],
            "warnings": [],
            "retry_tools": [],
            "retry_instruction_ko": "",
        },
    }


def test_sports_motion_request_routes_to_sports_playbook() -> None:
    registry = load_builtin_registry()

    decision = dispatch_request(registry, "강지연 최근 기록으로 운동퍼포먼스 제멀 분석 리포트 줘")

    assert decision.playbook_key == "sports_motion_analysis"
    assert decision.required_tools[0] == "sports_motion_report_package"
    assert "execute_code" in decision.forbidden_tools


def test_max_api_success_payload_contains_governance_reviewer(monkeypatch) -> None:
    monkeypatch.setenv("MAX_ANALYSIS_VARIABLES_API_KEY", "test-token")
    monkeypatch.setattr(
        "plugins.sports_performance.max_analysis_api._fetch_page",
        lambda **_: {
            "ok": True,
            "records": [
                {
                    "student_name": "강지연",
                    "sport": "slj",
                    "variable_key": "takeoff_angle",
                    "variable_name": "뛰어오르는 각도",
                    "unit": "deg",
                }
            ],
        },
    )

    payload = build_max_analysis_variables_response({"student_name": "강지연", "sport": "제멀"})

    assert payload["ok"] is True
    assert payload["source"] == "max_analysis_variables_api"
    assert payload["reviewer"]["name"] == "sports_max_api_reviewer"
    assert payload["reviewer"]["status"] == "pass"
    assert "API 원천" in payload["reviewer"]["checked"]


def test_governance_records_sports_max_api_pass() -> None:
    recorded = []

    transformed = governance_transform_tool_result(
        tool_name="sports_max_analysis_variables",
        result=json.dumps(_max_api_payload(), ensure_ascii=False),
        governance_ledger_recorder=recorded.append,
        request_id="sports-smoke",
    )

    assert transformed is None
    assert len(recorded) == 1
    entry = recorded[0]
    assert entry.playbook_key == "sports_motion_analysis"
    assert entry.tools_used == ("sports_max_analysis_variables",)
    assert entry.review_status == "pass"
    assert entry.failures == ()


def test_registered_sports_feedback_handler_self_reviews_before_governance() -> None:
    raw = make_feedback_tool_handler(None)(
        {
            "student_name": "강지연",
            "exercise": "제멀",
            "metrics": {"발사각": 22, "무릎각도": 126},
            "records": {"latest": 205},
        }
    )
    payload = json.loads(raw)

    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="sports_motion_analysis",
        tool_name="sports_motion_feedback",
        result=raw,
    )

    assert payload["reviewer"]["name"] == "sports_performance_reviewer"
    assert payload["reviewer"]["status"] == "retry_needed"
    assert outcome.reason == "reviewer_retry_needed"


def test_governance_sports_retry_passes_evidence_refs_to_feedback(monkeypatch) -> None:
    captured_feedback_args = []

    def fake_dispatch(tool_name: str, args: dict, **_: object) -> str:
        if tool_name == "sports_pe_brain_evidence":
            return json.dumps(
                {
                    "ok": True,
                    "packs": [
                        {
                            "id": "sports_ref:slj-arm-swing",
                            "quality_status": "accepted",
                            "exercise_keys": ["standing_long_jump"],
                        }
                    ],
                },
                ensure_ascii=False,
            )
        if tool_name == "sports_motion_feedback":
            captured_feedback_args.append(dict(args))
            return json.dumps(
                {
                    "ok": True,
                    "student_name": args.get("student_name"),
                    "exercise": {"key": "standing_long_jump"},
                    "normalized_metrics": args.get("metrics") or {},
                    "coach_output": {
                        "summary": "근거팩 기반 제멀 피드백",
                        "bottlenecks": ["발사각 보정"],
                        "technical_cues": ["팔스윙 타이밍"],
                        "drills": ["암스윙 브로드점프"],
                        "one_week_plan": ["주 2회 기술 반복"],
                        "avoid": ["통증 시 중단"],
                    },
                    "safety": {"status": "ok"},
                    "evidence_status": "source_pack_linked",
                    "reviewer": {
                        "name": "sports_performance_reviewer",
                        "status": "pass",
                        "checked": ["학생/종목/지표", "기술 피드백 구조", "안전 문구", "논문 근거 연결 상태"],
                    },
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"unexpected retry tool: {tool_name}")

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)
    raw = json.dumps(
        {
            "ok": True,
            "student_name": "강지연",
            "exercise": {"key": "standing_long_jump"},
            "normalized_metrics": {"launch_angle": 22},
            "coach_output": {
                "summary": "근거팩 연결 전 피드백",
                "bottlenecks": ["발사각 보정"],
                "technical_cues": ["팔스윙 타이밍"],
                "drills": ["암스윙 브로드점프"],
                "one_week_plan": ["주 2회 기술 반복"],
                "avoid": ["통증 시 중단"],
            },
            "safety": {"status": "ok"},
            "evidence_status": "pending_source_pack",
            "reviewer": {
                "name": "sports_performance_reviewer",
                "status": "retry_needed",
                "checked": ["학생/종목/지표", "기술 피드백 구조", "안전 문구", "논문 근거 연결 상태"],
                "retry_tools": ["sports_pe_brain_evidence", "sports_motion_feedback"],
                "retry_args": [
                    {"tool": "sports_pe_brain_evidence", "args": {"exercise": "standing_long_jump", "limit": 5}},
                    {
                        "tool": "sports_motion_feedback",
                        "args": {
                            "student_name": "강지연",
                            "exercise": "standing_long_jump",
                            "metrics": {"launch_angle": 22},
                        },
                    },
                ],
                "retry_instruction_ko": "PE-brain 근거팩을 먼저 검색한 뒤 같은 운동 피드백 도구를 다시 실행해 주세요.",
            },
        },
        ensure_ascii=False,
    )

    transformed = governance_transform_tool_result(
        tool_name="sports_motion_feedback",
        result=raw,
        governance_skip_ledger=True,
    )

    assert transformed is not None
    assert json.loads(transformed)["reviewer"]["status"] == "pass"
    assert captured_feedback_args[0]["evidence_refs"] == ["sports_ref:slj-arm-swing"]
    assert captured_feedback_args[0]["exercise"] == "standing_long_jump"
    assert captured_feedback_args[0]["metrics"] == {"launch_angle": 22}
    assert "tool" not in captured_feedback_args[0]


def test_final_delivery_requires_and_accepts_sports_review_evidence() -> None:
    registry = load_builtin_registry()
    user_text = "강지연 최근 기록으로 운동퍼포먼스 제멀 분석 리포트 줘"
    response_text = "강지연 학생의 제멀 운동분석 결과, 뛰어오르는 각도가 우선 개선 포인트입니다."

    blocked = evaluate_final_delivery(registry, user_text=user_text, response_text=response_text, outcomes=[])
    assert blocked.action == "block"
    assert blocked.playbook_key == "sports_motion_analysis"

    max_only = evaluate_final_delivery(
        registry,
        user_text=user_text,
        response_text=response_text,
        outcomes=[
            {
                "playbook_key": "sports_motion_analysis",
                "tools_used": ["sports_max_analysis_variables"],
                "review_status": "pass",
                "failures": [],
            }
        ],
    )
    assert max_only.action == "block"
    assert max_only.reason == "review_evidence_missing"

    max_and_html_only = evaluate_final_delivery(
        registry,
        user_text=user_text,
        response_text=response_text,
        outcomes=[
            {
                "playbook_key": "sports_motion_analysis",
                "tools_used": ["sports_max_analysis_variables", "sports_report_html_template"],
                "review_status": "pass",
                "failures": [],
            }
        ],
    )
    assert max_and_html_only.action == "block"
    assert max_and_html_only.reason == "review_evidence_missing"

    allowed = evaluate_final_delivery(
        registry,
        user_text=user_text,
        response_text=response_text,
        outcomes=[
            {
                "playbook_key": "sports_motion_analysis",
                "tools_used": ["sports_motion_report_package"],
                "review_status": "pass",
                "failures": [],
            }
        ],
    )
    assert allowed.action == "allow"
    assert allowed.reason == "review_evidence_passed"


def test_governance_accepts_reviewed_sports_report_package_result() -> None:
    raw = json.dumps(
        {
            "ok": True,
            "success": True,
            "artifact_path": "/tmp/오윤지_제자리멀리뛰기_운동분석리포트.pdf",
            "media_tag": "MEDIA:`/tmp/오윤지_제자리멀리뛰기_운동분석리포트.pdf`",
            "max_analysis": {"ok": True, "source": "max_analysis_variables_api", "record_count": 48},
            "cohort_model": {
                "ok": True,
                "basis": "national_gender_elite_1pct_from_max_api",
                "cohort_session_count": 7,
                "elite_session_count": 1,
            },
            "feedback": {"reviewer": {"name": "sports_performance_reviewer", "status": "pass"}},
            "pdf": {
                "artifact_path": "/tmp/오윤지_제자리멀리뛰기_운동분석리포트.pdf",
                "reviewer": {"name": "html_pdf_quality_review", "status": "pass"},
            },
            "reviewer": {
                "name": "sports_performance_reviewer",
                "status": "pass",
                "checked": ["학생/종목/지표", "기술 피드백 구조", "안전 문구", "논문 근거 연결 상태", "PDF 품질 게이트"],
            },
        },
        ensure_ascii=False,
    )

    transformed = governance_transform_tool_result(
        tool_name="sports_motion_report_package",
        result=raw,
        governance_skip_ledger=True,
    )

    assert transformed is None


def test_final_delivery_blocks_missing_data_reply_after_sports_tool_evidence() -> None:
    registry = load_builtin_registry()
    user_text = "강지연 최근 기록으로 운동퍼포먼스 제멀 분석 리포트 줘"
    response_text = (
        "강지연 학생의 최근 제자리멀리뛰기 운동퍼포먼스 분석 리포트를 작성하려면 "
        "최근 측정 기록과 운동분석 변인값이 필요합니다."
    )

    decision = evaluate_final_delivery(
        registry,
        user_text=user_text,
        response_text=response_text,
        outcomes=[
            {
                "playbook_key": "sports_motion_analysis",
                "tools_used": ["sports_max_analysis_variables"],
                "review_status": "pass",
                "failures": [],
            },
            {
                "playbook_key": "sports_motion_analysis",
                "tools_used": ["sports_motion_feedback"],
                "review_status": "pass",
                "failures": [],
            },
        ],
    )

    assert decision.action == "block"
    assert decision.reason == "review_evidence_missing"
    assert "sports_motion_report_package" in decision.retry_tools
