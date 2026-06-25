"""Final delivery gate tests for governed Governance OS responses."""

from __future__ import annotations

import importlib
import json
from typing import Any, cast

from plugins.governance_os.delivery_gate import (
    evaluate_final_delivery,
    governance_transform_llm_output,
)
from plugins.governance_os.registry import load_builtin_registry


def _passed_outcome() -> dict[str, object]:
    return {
        "playbook_key": "susi_score_calculation",
        "review_status": "pass",
        "tools_used": ["susi27_score_calculate"],
        "failures": [],
    }


def _patch_auxiliary_review_pass(monkeypatch) -> list[dict[str, object]]:
    import plugins.governance_os.review as review

    calls: list[dict[str, Any]] = []

    def fake_auxiliary_reviewer(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        checked = kwargs.get("checked")
        return {
            "status": "pass",
            "checked": list(checked) if isinstance(checked, (list, tuple)) else [],
        }

    monkeypatch.setattr(review, "_call_auxiliary_reviewer", fake_auxiliary_reviewer)
    return calls


def _patch_auxiliary_review_broken(monkeypatch) -> list[dict[str, object]]:
    import plugins.governance_os.review as review

    calls: list[dict[str, object]] = []

    def broken_auxiliary_reviewer(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        raise RuntimeError("provider offline")

    monkeypatch.setattr(review, "_call_auxiliary_reviewer", broken_auxiliary_reviewer)
    return calls


def test_final_delivery_gate_blocks_score_claim_without_review_evidence() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_text="서연이 수시 환산점수 계산해줘",
        outcomes=[],
    )

    assert decision.action == "block"
    assert decision.playbook_key == "susi_score_calculation"
    assert decision.reason == "review_evidence_missing"
    assert decision.retry_tools == ("susi27_score_calculate",)
    assert "확인 근거" in decision.message_ko
    assert "후검증" not in decision.message_ko
    assert "전용 도구" not in decision.message_ko
    assert "Traceback" not in decision.message_ko


def test_final_delivery_gate_blocks_governed_answer_without_completion_keywords() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="서연이는 서울대 지역균형보다 한국체대 교과전형 쪽이 더 현실적입니다.",
        user_text="서연이 실기 추천해줘",
        outcomes=[],
    )

    assert decision.action == "block"
    assert decision.reason == "review_evidence_missing"
    assert decision.playbook_key == "academy_practical_recommendation"


def test_final_delivery_gate_blocks_response_routed_playbook_without_user_text() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="서연이 실기 추천 기준으로 보면 한국체대 교과전형이 더 현실적입니다.",
        outcomes=[],
    )

    assert decision.action == "block"
    assert decision.reason == "review_evidence_missing"
    assert decision.playbook_key == "academy_practical_recommendation"


def test_final_delivery_gate_allows_governance_review_markdown_summary() -> None:
    response = """
    # Governance OS 적대적 리뷰 정리

    남은 문제는 Final Delivery Gate 오탐, dispatcher 후보 제한,
    auxiliary reviewer latency입니다. 예시 단어로 수시 점수 계산,
    학종 리포트 PDF, 실기 추천, reviewer pass evidence를 언급해도
    이것은 개발 리뷰 문서이지 학생 산출물 최종 전달이 아닙니다.
    """

    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text=response,
        user_text="그럼 md 다시 줘봐 정리해서",
        outcomes=[],
    )

    assert decision.action == "allow"
    assert decision.reason == "governance_review_context"


def test_final_delivery_gate_blocks_governance_marked_score_claim_without_review() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text=(
            "Governance OS와 Final Delivery Gate 검토까지 끝났습니다. "
            "서연이 수시 환산점수는 947.3점입니다."
        ),
        user_text="그럼 md 다시 줘봐 정리해서",
        outcomes=[],
    )

    assert decision.action == "block"
    assert decision.playbook_key == "susi_score_calculation"
    assert decision.reason == "review_evidence_missing"


def test_final_delivery_gate_blocks_student_score_claim_in_governance_review_context() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="거버넌스 리뷰 기준으로 보면 서연 학생은 983.4점이고 가능권입니다.",
        user_text="그럼 md 다시 줘봐 정리해서 governance_os 리뷰 결과",
        outcomes=[],
    )

    assert decision.action == "block"
    assert decision.playbook_key == "susi_score_calculation"
    assert decision.reason == "review_evidence_missing"


def test_transform_llm_output_allows_governance_review_markdown_summary() -> None:
    transformed = governance_transform_llm_output(
        response_text=(
            "Governance OS 리뷰: Final Delivery Gate, dispatcher 후보 제한, "
            "수시 점수 계산과 PDF 예시는 오탐 재현용 문맥입니다."
        ),
        user_message="적대적 리뷰 md로 정리해줘",
        governance_outcomes=[],
    )

    assert transformed is None


def test_transform_llm_output_allows_general_model_release_question_with_tool_history() -> None:
    transformed = governance_transform_llm_output(
        response_text=(
            "GPT 5.6 출시 시점은 공식 발표가 없어 확정할 수 없습니다. "
            "공개 일정이 나오기 전까지는 추정으로만 봐야 합니다."
        ),
        user_message="gpt 5.6언제쯤나올까",
        conversation_history=[
            {
                "role": "user",
                "content": "다시 한번 수정했고, 다시한번 적대적 리뷰 해줘",
            },
            {
                "role": "assistant",
                "content": "Governance OS 리뷰 결과를 정리했습니다.",
            },
            {"role": "user", "content": "gpt 5.6언제쯤나올까"},
            {
                "role": "tool",
                "name": "terminal",
                "content": "2026-06-25 15:17:00 KST",
            },
        ],
    )

    assert transformed is None


def test_final_delivery_gate_allows_meta_question_about_governed_tools() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text=(
            "생기부 저장, 학종 PDF 리포트, 실기 추천 도구에는 "
            "도구별 reviewer subagent를 붙이는 방식을 추천합니다."
        ),
        user_text=(
            "생기부 저장이랑 학종 pdf 리포트, 실기추천 도구 만들 때도 "
            "서브에이전트를 쓰나?"
        ),
        outcomes=[],
    )

    assert decision.action == "allow"
    assert decision.reason == "not_final_delivery_claim"


def test_final_delivery_gate_blocks_terse_completion_for_governed_request() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="완료했습니다.",
        user_text="서연이 학종 리포트 PDF 만들어줘",
        outcomes=[],
    )

    assert decision.action == "block"
    assert decision.playbook_key == "academy_hakjong_report"
    assert decision.reason == "review_evidence_missing"


def test_final_delivery_gate_allows_score_claim_with_review_pass_evidence() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_text="서연이 수시 환산점수 계산해줘",
        outcomes=[_passed_outcome()],
    )

    assert decision.action == "allow"
    assert decision.reason == "review_evidence_passed"


def test_final_delivery_gate_blocks_rule_lookup_only_score_claim() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_text="서연이 수시 환산점수 계산해줘",
        outcomes=[
            {
                "playbook_key": "susi_score_calculation",
                "review_status": "pass",
                "tools_used": ["susi27_rule_lookup"],
                "failures": [],
            }
        ],
    )

    assert decision.action == "block"
    assert decision.reason == "review_evidence_missing"


def test_final_delivery_gate_allows_explanatory_non_final_response() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="수시 환산점수 계산은 전용 도구와 학생 과목 정보가 필요합니다.",
        user_text="수시 환산점수 계산 방법 알려줘",
        outcomes=[],
    )

    assert decision.action == "allow"
    assert decision.reason == "not_final_delivery_claim"


def test_final_delivery_gate_blocks_score_claim_even_with_progress_status() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="확인 중입니다. 서연이 수시 환산점수는 947.3점입니다.",
        user_text="서연이 수시 환산점수 계산해줘",
        outcomes=[],
    )

    assert decision.action == "block"
    assert decision.reason == "review_evidence_missing"


def test_transform_llm_output_rewrites_blocked_governed_response() -> None:
    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
    )

    assert transformed is not None
    assert "확인 근거" in transformed
    assert "후검증" not in transformed
    assert "전용 도구" not in transformed
    assert "susi27_score_calculate" not in transformed
    assert "Traceback" not in transformed


def test_transform_llm_output_uses_llm_repair_on_gateway_runtime(monkeypatch) -> None:
    import plugins.governance_os.final_qa as final_qa

    calls: list[dict[str, object]] = []

    def fake_repair(question: str, answer: str, *, evidence=None):
        calls.append({"question": question, "answer": answer, "evidence": evidence})
        return "서연이 수시 환산점수 답변은 확인을 다시 거쳐 이어서 전달하겠습니다."

    monkeypatch.setattr(final_qa, "repair_answer_until_pass", fake_repair)

    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
        platform="discord",
    )

    assert transformed == "서연이 수시 환산점수 답변은 확인을 다시 거쳐 이어서 전달하겠습니다."
    assert calls
    assert calls[0]["question"] == "서연이 수시 환산점수 계산해줘"
    evidence = calls[0]["evidence"]
    assert isinstance(evidence, dict)
    typed_evidence = cast("dict[str, object]", evidence)
    assert typed_evidence["reason"] == "review_evidence_missing"


def test_transform_llm_output_leaves_reviewed_response_unchanged() -> None:
    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[_passed_outcome()],
    )

    assert transformed is None


def test_transform_llm_output_allows_current_turn_reviewed_tool_result(monkeypatch) -> None:
    calls = _patch_auxiliary_review_pass(monkeypatch)

    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        conversation_history=[
            {"role": "user", "content": "서연이 수시 환산점수 계산해줘"},
            {
                "role": "tool",
                "name": "susi27_score_calculate",
                "content": json.dumps(
                    {
                        "status": "calculated",
                        "student_record_score": 947.3,
                        "reviewer": {
                            "name": "academy_result_reviewer",
                            "status": "pass",
                            "checked": ["필수 산출 필드", "상태값"],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    )

    assert transformed is None
    assert calls
    assert calls[0]["task"] == "miho_governance_reviewer"


def test_transform_llm_output_skips_auxiliary_for_low_risk_attachment_pass(
    monkeypatch,
) -> None:
    calls = _patch_auxiliary_review_broken(monkeypatch)

    transformed = governance_transform_llm_output(
        response_text="MHTML 파일을 첨부했습니다.",
        user_message="mhtml 파일 첨부해서 보내줘",
        conversation_history=[
            {"role": "user", "content": "mhtml 파일 첨부해서 보내줘"},
            {
                "role": "tool",
                "name": "media_delivery_contract",
                "content": json.dumps(
                    {
                        "success": True,
                        "artifact_path": "/tmp/report.mhtml",
                        "media_tag": "MEDIA:/tmp/report.mhtml",
                        "reviewer": {
                            "name": "attachment_delivery_review",
                            "status": "pass",
                            "checked": ["media_tag", "artifact_path"],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    )

    assert transformed is None
    assert calls == []


def test_transform_llm_output_ignores_previous_turn_tool_result() -> None:
    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        conversation_history=[
            {"role": "user", "content": "가은이 수시 환산점수 계산해줘"},
            {
                "role": "tool",
                "name": "susi27_score_calculate",
                "content": json.dumps(
                    {
                        "status": "calculated",
                        "student_record_score": 944.1,
                        "reviewer": {
                            "name": "academy_result_reviewer",
                            "status": "pass",
                            "checked": ["필수 산출 필드", "상태값"],
                        },
                    },
                    ensure_ascii=False,
                ),
            },
            {"role": "user", "content": "서연이 수시 환산점수 계산해줘"},
        ],
    )

    assert transformed is not None
    assert "확인 근거" in transformed
    assert "후검증" not in transformed
    assert "전용 도구" not in transformed


def test_final_delivery_gate_blocks_internal_guard_instruction_leak() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text=(
            "전용 도구/후검증 통과 기록이 없어 최종 전달할 수 없습니다. "
            "결과를 전달하지 말고 같은 전용 도구로 다시 실행해야 합니다."
        ),
        user_text="안시현 학종 리포트 만들어줘",
        outcomes=[],
    )

    assert decision.action == "block"
    assert decision.reason == "internal_guard_leak"
    assert "후검증" not in decision.message_ko
    assert "전용 도구" not in decision.message_ko
    assert "다시 실행해야" not in decision.message_ko


def test_final_delivery_gate_blocks_governance_json_key_leak() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text='{"next_action": "retry_required", "retry_tools": ["susi27_score_calculate"]}',
        user_text="서연이 점수 계산해줘",
        outcomes=[],
    )

    assert decision.action == "block"
    assert decision.reason == "internal_guard_leak"


def test_final_delivery_gate_allows_plain_tool_mention_without_leak() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="수시 환산점수 계산은 전용 도구와 학생 과목 정보가 필요합니다.",
        user_text="수시 환산점수 계산 방법 알려줘",
        outcomes=[],
    )

    assert decision.action == "allow"
    assert decision.reason == "not_final_delivery_claim"


def test_final_delivery_gate_allows_review_doc_quoting_guard_phrase() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text=(
            "# Governance OS 적대적 리뷰\n"
            "차단 문구 '전용 도구를 다시 실행해야 합니다'가 safe_markers 때문에 "
            "그대로 새는 게 문제다. dispatcher 후보 제한과 오탐도 함께 본다."
        ),
        user_text="적대적 리뷰 결과 정리해줘",
        outcomes=[],
    )

    assert decision.action == "allow"
    assert decision.reason == "governance_review_context"


def test_transform_llm_output_repairs_internal_guard_leak() -> None:
    transformed = governance_transform_llm_output(
        response_text=(
            "후검증을 통과하지 못했습니다. 결과를 전달하지 말고 "
            "전용 도구를 다시 실행해야 합니다."
        ),
        user_message="안시현 학종 리포트 만들어줘",
        governance_outcomes=[],
    )

    assert transformed is not None
    assert "후검증" not in transformed
    assert "전용 도구" not in transformed
    assert "다시 실행해야" not in transformed


def test_final_delivery_gate_allows_general_coding_answer_with_rerun_phrase() -> None:
    # 미호는 범용 OS다. 일반 코딩 답변에 "다시 실행" 같은 표현이 있어도 차단 금지.
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text=(
            "빌드가 실패하면 의존성을 정리한 뒤 `npm run build`를 다시 실행해야 합니다. "
            "그래도 안 되면 캐시를 지우고 다시 시도하세요."
        ),
        user_text="next.js 빌드 에러 어떻게 고쳐?",
        outcomes=[],
    )

    assert decision.action == "allow"


def test_final_delivery_gate_allows_api_design_mentioning_next_action_field() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text=(
            "응답 스키마에 next_action 필드를 추가하고, 재시도가 필요하면 "
            "retry_tools 목록을 함께 내려주는 설계를 추천합니다."
        ),
        user_text="REST 응답 스키마 어떻게 설계하면 좋을까?",
        outcomes=[],
    )

    assert decision.action == "allow"


def test_final_delivery_gate_allows_plain_general_knowledge_answer() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="파이썬의 GIL은 한 번에 하나의 스레드만 바이트코드를 실행하게 합니다.",
        user_text="파이썬 GIL이 뭐야?",
        outcomes=[],
    )

    assert decision.action == "allow"
    assert decision.reason == "no_governed_playbook"


def test_transform_llm_output_allows_general_coding_answer() -> None:
    transformed = governance_transform_llm_output(
        response_text=(
            "리액트 상태가 안 바뀌면 useEffect 의존성 배열을 확인하고 "
            "필요하면 컴포넌트를 다시 렌더링하도록 key를 바꿔보세요."
        ),
        user_message="리액트 state 안 바뀌는 버그 어떻게 잡아?",
        governance_outcomes=[],
    )

    assert transformed is None


def test_final_delivery_gate_blocks_zero_width_obfuscated_guard_leak() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text=(
            "후​검증을 통과하지 못했습니다. 결과를 전달하지 말고 "
            "전용 도구를 다시 실행해야 합니다."
        ),
        user_text="안시현 학종 리포트 만들어줘",
        outcomes=[],
    )

    assert decision.action == "block"
    assert decision.reason == "internal_guard_leak"


def test_final_delivery_gate_allows_general_tech_score_without_admission_context() -> None:
    # 범용성: 학원 도메인 맥락(수시/환산/학종 등)이 없는 일반 기술 점수는 차단 금지.
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="대학 데이터베이스 동시 접속 처리량은 95점대 성능을 안정적으로 보였습니다.",
        user_text="대학 포털 데이터베이스 벤치마크 비교해줘",
        outcomes=[],
    )

    assert decision.action == "allow"
    assert decision.reason == "no_governed_playbook"


def test_transform_llm_output_strips_broken_attachment(monkeypatch) -> None:
    import plugins.governance_os.final_delivery_repair as repair_mod

    def fake_repair(path: str, **_kw: object) -> object:
        return repair_mod.FinalDeliveryRepairResult(
            status="blocked",
            message_ko="첨부할 파일을 확인할 수 없습니다.",
        )

    monkeypatch.setattr(repair_mod, "repair_artifact_delivery", fake_repair)

    transformed = governance_transform_llm_output(
        response_text="리포트입니다.\nMEDIA:`/Users/etlab/missing/report.xlsx`",
        user_message="리포트 첨부해줘",
        governance_outcomes=[],
    )

    assert transformed is not None
    assert "/Users/etlab/missing/report.xlsx" not in transformed
    assert "MEDIA:" not in transformed
    assert "확인할 수 없어" in transformed


def test_transform_llm_output_repairs_attachment_path(monkeypatch) -> None:
    import plugins.governance_os.final_delivery_repair as repair_mod

    def fake_repair(path: str, **_kw: object) -> object:
        return repair_mod.FinalDeliveryRepairResult(
            status="repaired",
            artifact_path="/safe/cache/governance_delivery/report-abc123.xlsx",
            staged_path="/safe/cache/governance_delivery/report-abc123.xlsx",
            media_tag="MEDIA:`/safe/cache/governance_delivery/report-abc123.xlsx`",
        )

    monkeypatch.setattr(repair_mod, "repair_artifact_delivery", fake_repair)

    transformed = governance_transform_llm_output(
        response_text="안시현 학종 리포트입니다.\nMEDIA:`/Users/etlab/reports/ansh.xlsx`",
        user_message="안시현 학종 리포트 첨부해줘",
        governance_outcomes=[],
    )

    assert transformed is not None
    assert "/safe/cache/governance_delivery/report-abc123.xlsx" in transformed
    assert "/Users/etlab/reports/ansh.xlsx" not in transformed


def test_transform_llm_output_leaves_already_deliverable_attachment(monkeypatch) -> None:
    import plugins.governance_os.final_delivery_repair as repair_mod

    def fake_repair(path: str, **_kw: object) -> object:
        return repair_mod.FinalDeliveryRepairResult(
            status="already_allowed",
            artifact_path=path,
            media_tag=f"MEDIA:`{path}`",
        )

    monkeypatch.setattr(repair_mod, "repair_artifact_delivery", fake_repair)

    transformed = governance_transform_llm_output(
        response_text="첨부 파일입니다.\nMEDIA:`/already/safe/report.xlsx`",
        user_message="리포트 첨부해줘",
        governance_outcomes=[],
    )

    assert transformed is None


def test_final_delivery_gate_does_not_trust_stale_global_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants
    from agent import evolution
    from plugins.governance_os.ledger import OutcomeLedgerEntry, record_outcome

    importlib.reload(miho_constants)
    importlib.reload(evolution)
    record_outcome(
        OutcomeLedgerEntry(
            request_id="previous-unrelated-score-request",
            playbook_key="susi_score_calculation",
            tools_used=("susi27_score_calculate",),
            review_status="pass",
        )
    )

    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_text="서연이 수시 환산점수 계산해줘",
    )

    assert decision.action == "block"
    assert decision.reason == "review_evidence_missing"
