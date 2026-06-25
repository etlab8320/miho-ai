"""Live regression coverage for Governance OS delivery failures."""

from __future__ import annotations

import json

from plugins.governance_os.delivery_gate import governance_transform_llm_output


_SELF_BLOCKING_SNIPPETS = (
    "그대로 전달하지 않겠습니다",
    "필요한 확인을 다시 거쳐 이어서",
    "최종 전달할 수 없습니다",
    "후검증",
    "전용 도구",
)


def _assert_no_self_blocking_text(text: str | None) -> None:
    rendered = str(text or "")
    assert rendered.strip()
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
    transformed = governance_transform_llm_output(
        response_text=(
            "방금 답변은 확인 근거가 충분하지 않아 그대로 전달하지 않겠습니다. "
            "필요한 확인을 다시 거쳐 이어서 답하겠습니다."
        ),
        user_message="미호를 진짜 완벽하게 거버넌스os+셀프업그레이드하네스 구조로 만들었어. 적대적 리뷰해줘",
        governance_outcomes=[],
    )

    _assert_no_self_blocking_text(transformed)


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


def test_runtime_repair_pass_is_filtered_if_it_returns_self_blocking_phrase(monkeypatch) -> None:
    def bad_repair(*_args: object, **_kwargs: object) -> str:
        return (
            "방금 답변은 확인 근거가 충분하지 않아 그대로 전달하지 않겠습니다. "
            "필요한 확인을 다시 거쳐 이어서 답하겠습니다."
        )

    monkeypatch.setattr("plugins.governance_os.final_qa.repair_answer_until_pass", bad_repair)

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
