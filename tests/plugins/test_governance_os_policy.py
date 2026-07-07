"""Policy guard tests for Governance OS tool contracts."""

from __future__ import annotations

from plugins.governance_os.guard import governance_pre_tool_call
from plugins.governance_os.policy import evaluate_tool_call
from plugins.governance_os.registry import load_builtin_registry


def test_policy_blocks_forbidden_command_inside_terminal_args() -> None:
    decision = evaluate_tool_call(
        load_builtin_registry(),
        playbook_key="dev_code_update",
        tool_name="terminal",
        args={"command": "git reset --hard"},
    )

    assert decision.action == "block"
    assert decision.reason == "forbidden_tool"
    assert decision.tool_name == "terminal"
    assert "전용 도구" in decision.message_ko


def test_policy_blocks_forbidden_tool_with_plain_korean_message() -> None:
    decision = evaluate_tool_call(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="execute_code",
        args={"code": "make a hakjong PDF manually"},
    )

    assert decision.action == "block"
    assert decision.playbook_key == "academy_hakjong_report"
    assert decision.tool_name == "execute_code"
    assert "전용 도구" in decision.message_ko
    assert "Traceback" not in decision.message_ko
    assert "pre_tool_call" not in decision.message_ko


def test_policy_requires_review_for_high_risk_required_tool() -> None:
    decision = evaluate_tool_call(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        args={"student_name": "가은"},
    )

    assert decision.action == "review_required"
    assert decision.reason == "review_gate_required"
    assert "academy_result_reviewer" in decision.review_gates


def test_policy_requires_review_for_susi_score_calculation_tool() -> None:
    decision = evaluate_tool_call(
        load_builtin_registry(),
        playbook_key="susi_score_calculation",
        tool_name="susi27_score_calculate",
        args={"student_name": "서연", "target_university": "서경대"},
    )

    assert decision.action == "review_required"
    assert "academy_result_reviewer" in decision.review_gates


def test_pre_tool_guard_blocks_destructive_git_command_without_playbook_text() -> None:
    result = governance_pre_tool_call(
        tool_name="terminal",
        args={"command": "git checkout -- ."},
    )

    assert result is not None
    assert result["action"] == "block"
    assert "전용 도구" in result["message"]


def test_governance_pre_tool_guard_blocks_playbook_forbidden_tool() -> None:
    result = governance_pre_tool_call(
        tool_name="write_file",
        args={
            "path": "report.pdf",
            "content": "가은이 학종 리포트 PDF를 직접 만들어줘",
        },
    )

    assert result is not None
    assert result["action"] == "block"
    assert "전용 도구" in result["message"]
    assert "Traceback" not in result["message"]


def test_governance_pre_tool_guard_ignores_unmatched_general_tool() -> None:
    result = governance_pre_tool_call(
        tool_name="write_file",
        args={"path": "notes.txt", "content": "일반 메모"},
    )

    assert result is None


def test_governance_pre_tool_guard_never_blocks_skill_manage_housekeeping() -> None:
    result = governance_pre_tool_call(
        tool_name="skill_manage",
        args={
            "action": "patch",
            "name": "miho-agent",
            "old_string": "fallback",
            "new_string": "LLM fail-closed path",
        },
        user_text="거버넌스 가드가 스킬매니지를 막으면 안 된다. 스킬을 보강해라.",
    )

    assert result is None


def test_governance_pre_tool_guard_blocks_forbidden_tool_from_turn_context() -> None:
    result = governance_pre_tool_call(
        tool_name="execute_code",
        args={"code": "print('fallback calculation')"},
        user_text=(
            "강지연 최근 기록으로 운동퍼포먼스 제멀 분석 리포트 줘\n\n"
            "Governance OS routing:\n"
            "- playbook: sports_motion_analysis\n"
            "- required_tools: sports_max_analysis_variables, sports_motion_feedback\n"
        ),
    )

    assert result is not None
    assert result["action"] == "block"
    assert "전용 도구" in result["message"]


def test_governance_pre_tool_guard_reads_current_turn_context() -> None:
    from agent.turn_context import set_current_user_message

    set_current_user_message(
        "강지연 최근 기록으로 운동퍼포먼스 제멀 분석 리포트 줘\n\n"
        "Governance OS routing:\n"
        "- playbook: sports_motion_analysis\n"
    )

    result = governance_pre_tool_call(
        tool_name="execute_code",
        args={"code": "print('manual sports fallback')"},
    )

    assert result is not None
    assert result["action"] == "block"


def test_governance_pre_tool_guard_does_not_block_docs_patch_mentions() -> None:
    result = governance_pre_tool_call(
        tool_name="apply_patch",
        args={"patch": "docs: 학종 리포트 playbook 설명을 보강한다"},
    )

    assert result is None


def test_governance_pre_tool_guard_allows_governance_pytest_review_command() -> None:
    result = governance_pre_tool_call(
        tool_name="terminal",
        args={
            "command": (
                "python -m pytest tests/plugins/test_governance_os_delivery_gate.py "
                "-k '수시 or 환산 or PDF'"
            )
        },
    )

    assert result is None


def test_governance_pre_tool_guard_allows_governance_introspection_command() -> None:
    result = governance_pre_tool_call(
        tool_name="terminal",
        args={
            "command": (
                "python - <<'PY'\n"
                "from plugins.governance_os.delivery_gate import evaluate_final_delivery\n"
                "print('Final Delivery Gate 수시 점수 계산 실기 추천 학종 리포트 PDF 직접 계산 오탐 검증')\n"
                "PY"
            )
        },
    )

    assert result is None


def test_governance_pre_tool_guard_allows_governance_live_check_command() -> None:
    result = governance_pre_tool_call(
        tool_name="terminal",
        args={
            "command": (
                ".venv/bin/miho governance live-check --mode live "
                "--target discord:1507988401171857521:1521079781242704033 --json"
            )
        },
    )

    assert result is None


def test_governance_pre_tool_guard_allows_pytest_commands_for_domain_named_tests() -> None:
    result = governance_pre_tool_call(
        tool_name="terminal",
        args={
            "command": (
                ".venv/bin/python -m pytest -o addopts='' "
                "tests/plugins/test_susi_ops_service.py tests/plugins/test_academy_remote_auth.py -q"
            )
        },
    )

    assert result is None


def test_governance_pre_tool_guard_blocks_governance_heredoc_artifact_bypass() -> None:
    result = governance_pre_tool_call(
        tool_name="terminal",
        args={
            "command": (
                "python - <<'PY'\n"
                "# plugins/governance_os regression probe\n"
                "print('가은이 학종 리포트 PDF를 reportlab으로 직접 생성')\n"
                "PY"
            )
        },
    )

    assert result is not None
    assert result["action"] == "block"
    assert "전용 도구" in result["message"]


def test_governance_pre_tool_guard_blocks_completed_pdf_generation_bypass() -> None:
    result = governance_pre_tool_call(
        tool_name="terminal",
        args={
            "cmd": (
                "python - <<'PY'\n"
                "# plugins/governance_os regression probe\n"
                "print('서연이 실기 추천 PDF 생성 완료했습니다')\n"
                "PY"
            )
        },
    )

    assert result is not None
    assert result["action"] == "block"
    assert "전용 도구" in result["message"]
