"""Live regression coverage for Governance OS delivery failures."""

from __future__ import annotations

import json
from typing import cast

from plugins.governance_os.delivery_gate import governance_transform_llm_output


_SELF_BLOCKING_SNIPPETS = (
    "확정 검수 전",
    "같은 요청을 다시",
    "그대로 전달하지 않겠습니다",
    "필요한 확인을 다시 거쳐 이어서",
    "최종 전달할 수 없습니다",
    "후검증",
    "전용 도구",
    "확인할 근거가 없어",
    "전달하긴 어려워",
)


def _assert_no_self_blocking_text(text: str | None) -> None:
    rendered = str(text or "")
    for snippet in _SELF_BLOCKING_SNIPPETS:
        assert snippet not in rendered


def test_blocked_governed_response_does_not_surface_self_blocking_fallback() -> None:
    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
    )

    _assert_no_self_blocking_text(transformed)


def test_live_self_blocking_phrase_is_repaired_even_in_review_request() -> None:
    def fake_call_llm(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {"content": '{"action":"revise","answer":"미호 Governance OS 적대적 리뷰 결과입니다."}'}

    def extract(response: object) -> str:
        assert isinstance(response, dict)
        typed = cast("dict[str, object]", response)
        return str(typed.get("content") or "")

    transformed = governance_transform_llm_output(
        response_text=(
            "방금 답변은 확인 근거가 충분하지 않아 그대로 전달하지 않겠습니다. "
            "필요한 확인을 다시 거쳐 이어서 답하겠습니다."
        ),
        user_message="미호를 진짜 완벽하게 거버넌스os+셀프업그레이드하네스 구조로 만들었어. 적대적 리뷰해줘",
        governance_outcomes=[],
        final_delivery_call_llm=fake_call_llm,
        final_delivery_extract_content=extract,
    )

    _assert_no_self_blocking_text(transformed)
    assert transformed == "미호 Governance OS 적대적 리뷰 결과입니다."


def test_governance_review_with_academy_terms_returns_review_not_fallback() -> None:
    answer = (
        "# 미호 Governance OS 적대적 리뷰\n"
        "Final Delivery Gate UX 안정성: 72점\n"
        "수시/학종/첨부 도메인의 reviewer evidence가 없으면 점수와 리포트 생성을 막아야 한다.\n"
        "Self-Harness 자동 개선 루프: 81점\n"
        "남은 리스크: 리뷰 요청의 평가 문장을 실제 산출물 전달로 오판하면 안 된다."
    )

    transformed = governance_transform_llm_output(
        response_text=answer,
        user_message="미호를 진짜 완벽하게 거버넌스os+ 셀프업그레이드하네스 구조로 만들었어! 적대적 리뷰를 해봐",
        governance_outcomes=[],
    )

    assert transformed is None


def test_governance_review_sanitizes_fallback_phrase_without_dropping_result() -> None:
    answer = (
        "# 미호 Governance OS 적대적 리뷰\n"
        "High: Final Delivery가 결과 대신 `확인 근거를 다시 모아 답변을 정리합니다. "
        "확정 점수나 첨부 완료처럼 검증이 필요한 결과는 검증된 값으로만 말하겠습니다.` 를 "
        "사용자에게 보여주는 위험이 있다.\n"
        "수정안: 리뷰 요청에서는 결과 본문을 유지하고 내부 차단 문장만 제거해야 한다."
    )

    def fake_call_llm(*_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "content": (
                '{"action":"revise","answer":"# 미호 Governance OS 적대적 리뷰\\n'
                'High: Final Delivery가 결과 대신 내부 보류 문구를 사용자에게 보여주는 위험이 있다.\\n'
                '수정안: 리뷰 요청에서는 결과 본문을 유지해야 한다."}'
            )
        }

    def extract(response: object) -> str:
        assert isinstance(response, dict)
        typed = cast("dict[str, object]", response)
        return str(typed.get("content") or "")

    transformed = governance_transform_llm_output(
        response_text=answer,
        user_message="미호 governance os 적대적 리뷰해줘",
        governance_outcomes=[],
        final_delivery_call_llm=fake_call_llm,
        final_delivery_extract_content=extract,
    )

    assert transformed is not None
    assert "미호 Governance OS 적대적 리뷰" in transformed
    assert "Final Delivery" in transformed
    assert "확인 근거를 다시 모아" not in transformed
    assert "확정 점수나 첨부 완료처럼" not in transformed


def test_runtime_repair_failure_does_not_surface_self_blocking_fallback(monkeypatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("provider down")

    monkeypatch.setattr("agent.auxiliary_client.call_llm", boom)

    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
        platform="discord",
    )

    _assert_no_self_blocking_text(transformed)


def test_runtime_repair_failure_records_self_harness_signal(monkeypatch) -> None:
    def boom(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("provider down")

    recorded: list[dict[str, object]] = []

    def fake_record_quality_failure(**kwargs: object) -> dict[str, object]:
        recorded.append(kwargs)
        return {"id": 1}

    monkeypatch.setattr("agent.auxiliary_client.call_llm", boom)
    monkeypatch.setattr(
        "plugins.governance_os.feedback_events.record_quality_failure",
        fake_record_quality_failure,
    )

    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
        platform="discord",
        session_id="delivery-recovery-test",
    )

    _assert_no_self_blocking_text(transformed)
    assert recorded
    assert recorded[0]["failure_signature"] == "final_delivery_recovery_transport_unavailable"
    assert recorded[0]["playbook_key"] == "susi_score_calculation"


def test_runtime_repair_pass_is_filtered_if_it_returns_self_blocking_phrase(monkeypatch) -> None:
    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 947.3점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
        platform="discord",
    )

    _assert_no_self_blocking_text(transformed)


def test_missing_tool_media_directive_is_repaired_before_gateway_append(monkeypatch) -> None:
    import plugins.governance_os.final_delivery_repair as repair_mod

    def fake_repair(path: str, **_kwargs: object) -> object:
        assert path == "/tmp/report.mhtml"
        return repair_mod.FinalDeliveryRepairResult(
            status="repaired",
            artifact_path="/Users/etlab/.miho/cache/media/governance_delivery/report-safe.mhtml",
            staged_path="/Users/etlab/.miho/cache/media/governance_delivery/report-safe.mhtml",
            media_tag="MEDIA:`/Users/etlab/.miho/cache/media/governance_delivery/report-safe.mhtml`",
        )

    monkeypatch.setattr(repair_mod, "repair_artifact_delivery", fake_repair)
    monkeypatch.setattr(
        "plugins.governance_os.review._call_auxiliary_reviewer",
        lambda **_kwargs: {
            "status": "pass",
            "checked": ["media_tag", "artifact_path"],
        },
    )
    tool_payload = {
        "success": True,
        "artifact_path": "/tmp/report.mhtml",
        "media_tag": "MEDIA:/tmp/report.mhtml",
        "reviewer": {"status": "pass", "checked": ["media_tag", "artifact_path"]},
    }

    transformed = governance_transform_llm_output(
        response_text="MHTML 파일을 첨부했습니다.",
        user_message="mhtml 파일 첨부해서 보내줘",
        conversation_history=[
            {"role": "user", "content": "mhtml 파일 첨부해서 보내줘"},
            {
                "role": "tool",
                "name": "media_delivery_contract",
                "content": json.dumps(tool_payload, ensure_ascii=False),
            },
        ],
    )

    assert transformed is not None
    assert "MEDIA:`/Users/etlab/.miho/cache/media/governance_delivery/report-safe.mhtml`" in transformed
    assert "MEDIA:/tmp/report.mhtml" not in transformed


def test_missing_tool_media_does_not_keep_attachment_completion_claim() -> None:
    tool_payload = {
        "success": True,
        "artifact_path": "/tmp/missing-report.mhtml",
        "media_tag": "MEDIA:/tmp/missing-report.mhtml",
        "reviewer": {"status": "pass", "checked": ["media_tag", "artifact_path"]},
    }

    transformed = governance_transform_llm_output(
        response_text="MHTML 파일을 첨부했습니다.",
        user_message="mhtml 파일 첨부해서 보내줘",
        conversation_history=[
            {"role": "user", "content": "mhtml 파일 첨부해서 보내줘"},
            {
                "role": "tool",
                "name": "media_delivery_contract",
                "content": json.dumps(tool_payload, ensure_ascii=False),
            },
        ],
    )

    assert transformed is not None
    assert "MEDIA:" not in transformed
    assert "첨부했습니다" not in transformed
    assert "확인할 수 없어" in transformed
