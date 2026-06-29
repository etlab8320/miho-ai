import pytest

from gateway import progress_copy


@pytest.mark.asyncio
async def test_generate_gateway_progress_copy_uses_auxiliary_llm(monkeypatch):
    captured = {}

    async def fake_call_llm(**kwargs):
        captured.update(kwargs)
        return object()

    def fake_extract(_response):
        return "  확인했어. 자료 구조 먼저 훑고 바로 이어서 볼게.  "

    import agent.auxiliary_client as auxiliary_client

    monkeypatch.setattr(auxiliary_client, "async_call_llm", fake_call_llm)
    monkeypatch.setattr(auxiliary_client, "extract_content_or_reasoning", fake_extract)

    text = await progress_copy.generate_gateway_progress_copy(
        kind="ack",
        user_message="이거 llm이 상황 맞춰서 대답하게 해줘",
        status={"api_call_count": 0, "max_iterations": 90, "current_tool": "terminal", "secret": "DROP"},
        timeout=1.5,
    )

    assert text == "확인했어. 자료 구조 먼저 훑고 바로 이어서 볼게."
    assert captured["task"] == "progress_copy"
    assert captured["max_tokens"] == 80
    assert captured["timeout"] == 1.5
    payload_text = captured["messages"][1]["content"]
    assert "api_call_count" in payload_text
    assert "current_tool" in payload_text
    assert "secret" not in payload_text


@pytest.mark.asyncio
async def test_generate_gateway_progress_copy_returns_none_when_llm_unavailable(monkeypatch):
    async def fake_call_llm(**_kwargs):
        raise RuntimeError("provider unavailable")

    import agent.auxiliary_client as auxiliary_client

    monkeypatch.setattr(auxiliary_client, "async_call_llm", fake_call_llm)

    assert await progress_copy.generate_gateway_progress_copy(
        kind="long_running",
        user_message="계속 진행상황 말해줘",
        status={"elapsed_minutes": 2},
        timeout=0.1,
    ) is None


def test_clean_one_liner_truncates_and_removes_fences():
    text = progress_copy._clean_one_liner("```json\n" + "가" * 300 + "\n```", max_chars=40)

    assert "```" not in text
    assert len(text) <= 40
    assert text.endswith("…")
