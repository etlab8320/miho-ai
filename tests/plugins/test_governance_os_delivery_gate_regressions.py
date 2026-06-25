"""Regression tests for Governance OS final delivery gate edge cases."""

from __future__ import annotations

import importlib
import json

from plugins.governance_os.delivery_gate import (
    evaluate_final_delivery,
    governance_transform_llm_output,
)
from plugins.governance_os.registry import load_builtin_registry


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


def test_final_delivery_gate_blocks_live_self_blocking_phrase_even_when_quoted() -> None:
    decision = evaluate_final_delivery(
        load_builtin_registry(),
        response_text=(
            "차단 문구 '방금 답변은 확인 근거가 충분하지 않아 그대로 전달하지 않겠습니다. "
            "필요한 확인을 다시 거쳐 이어서 답하겠습니다.' 가 재출현했다."
        ),
        user_text="미호 governance os 적대적 리뷰해줘",
        outcomes=[],
    )

    assert decision.action == "block"
    assert decision.reason == "internal_guard_leak"
    assert "그대로 전달하지 않겠습니다" not in decision.message_ko


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
    assert "리포트입니다" in transformed
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
