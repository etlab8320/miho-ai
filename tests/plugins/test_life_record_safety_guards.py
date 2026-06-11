"""Safety guard tests for life-record tools."""

from __future__ import annotations

from types import SimpleNamespace


def _event(text: str, chat_id: str = "thread-a") -> SimpleNamespace:
    source = SimpleNamespace(
        chat_id=chat_id,
        parent_chat_id="channel-1",
        guild_id="guild-1",
        chat_name=chat_id,
    )
    return SimpleNamespace(text=text, source=source)


def test_confirm_requires_explicit_review_phrase() -> None:
    from plugins.life_record.context import capture_gateway_context, user_requested_life_record_confirm

    capture_gateway_context(_event("중앙DB에 유가은 자료가 있는지 봐줘"))
    assert user_requested_life_record_confirm() is False

    capture_gateway_context(_event("원본 대조했고 검수 확정해줘"))
    assert user_requested_life_record_confirm() is True


def test_pre_tool_call_blocks_central_life_record_db_access() -> None:
    from plugins.life_record import _block_life_record_handcoding

    blocked = _block_life_record_handcoding(
        tool_name="terminal",
        args={"command": "sqlite3 ~/.miho/life_records/central.sqlite3 'select * from central_grades'"},
    )

    assert blocked and blocked["action"] == "block"
    assert _block_life_record_handcoding(
        tool_name="life_record_lookup",
        args={"query": "유가은"},
    ) is None


def test_pre_tool_call_allows_jungsi_tools_in_life_record_context() -> None:
    """문맥 키워드로 도구를 차단하지 않는다 — 의도 판단은 LLM (routing-v2)."""
    from plugins.life_record import _block_life_record_handcoding
    from plugins.life_record.context import capture_gateway_context

    capture_gateway_context(_event("유가은 학생 생기부를 왜 정시엔진에서 찾아... 학종 자료를 봐야지"))

    assert _block_life_record_handcoding(tool_name="jungsi_login", args={}) is None


def test_pre_tool_call_allows_score_calculation_in_susi_score_context() -> None:
    from plugins.life_record import _block_life_record_handcoding
    from plugins.life_record.context import capture_gateway_context

    capture_gateway_context(
        _event("종환이 점수로 내신환산이랑 작년 합격자 점수 보고 6개만 상향 중립 안전으로 뽑아줘")
    )

    assert _block_life_record_handcoding(tool_name="jungsi_student_university_score", args={}) is None


def test_pre_tool_call_allows_score_calculation_in_explicit_susi_context() -> None:
    from plugins.life_record import _block_life_record_handcoding
    from plugins.life_record.context import capture_gateway_context

    capture_gateway_context(_event("수시 교과 점수로 강원대 환산점수랑 전년도 컷 다시 계산해줘"))

    assert _block_life_record_handcoding(tool_name="jungsi_student_university_score", args={}) is None


def test_pre_tool_call_no_strict_turn_blocking() -> None:
    """라우팅 힌트가 있어도 다른 도구를 차단하지 않는다 (routing-v2)."""
    from plugins.life_record import _block_life_record_handcoding
    from plugins.life_record.context import capture_gateway_context

    capture_gateway_context(
        _event("[라우팅 힌트 — 참고용] 추천 도구: life_record_lookup")
    )

    assert _block_life_record_handcoding(tool_name="life_record_lookup", args={"query": "유가은"}) is None
    assert _block_life_record_handcoding(tool_name="session_search", args={"query": "유가은 학종"}) is None


def test_pre_tool_call_allows_jungsi_tools_outside_life_record_context() -> None:
    from plugins.life_record import _block_life_record_handcoding
    from plugins.life_record.context import capture_gateway_context

    capture_gateway_context(_event("정시엔진 로그인 링크 줘"))

    assert _block_life_record_handcoding(tool_name="jungsi_login", args={}) is None
