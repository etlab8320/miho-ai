from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from plugins.academy_ops import guidance_copy
from plugins.academy_ops.natural_router import AcademyNaturalRoute, resolve_and_execute_academy_request


@pytest.fixture(autouse=True)
def _enable_guidance_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIHO_ACADEMY_NATURAL_GUIDANCE_COPY", "1")


@pytest.mark.asyncio
async def test_guidance_copy_keeps_login_link(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(_messages: list[dict[str, str]]) -> str:
        return "좋아, 여기서 연결하면 돼.\nhttps://academy-login.etlab.kr/academy/login?state=abc"

    monkeypatch.setattr(guidance_copy, "_call_llm", fake_call)

    result = await guidance_copy.naturalize_guidance_response(
        user_text="파카 로그인 하자",
        intent="login_link",
        fallback="학원 계정 연결 링크를 만들었어.\nhttps://academy-login.etlab.kr/academy/login?state=abc",
    )

    assert result.startswith("좋아")
    assert "https://academy-login.etlab.kr/academy/login?state=abc" in result


@pytest.mark.asyncio
async def test_guidance_copy_falls_back_when_link_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(_messages: list[dict[str, str]]) -> str:
        return "로그인 링크를 만들었어. 여기서 연결하면 돼."

    fallback = "학원 계정 연결 링크를 만들었어.\nhttps://academy-login.etlab.kr/academy/login?state=abc"
    monkeypatch.setattr(guidance_copy, "_call_llm", fake_call)

    result = await guidance_copy.naturalize_guidance_response(
        user_text="파카 로그인 하자",
        intent="login_link",
        fallback=fallback,
    )

    assert result == fallback


@pytest.mark.asyncio
async def test_guidance_copy_falls_back_on_developer_terms(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_call(_messages: list[dict[str, str]]) -> str:
        return "401 오류라서 다시 로그인해야 해. `/academy login`으로 해줘."

    fallback = "학원 계정 연결이 필요해. `/academy login`으로 먼저 연결해줘."
    monkeypatch.setattr(guidance_copy, "_call_llm", fake_call)

    result = await guidance_copy.naturalize_guidance_response(
        user_text="기록 보여줘",
        intent="login_required",
        fallback=fallback,
    )

    assert result == fallback


@pytest.mark.asyncio
async def test_natural_router_uses_guidance_copy_for_not_ok_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolver(_messages: list[dict[str, str]]) -> object:
        return _response(
            {
                "action": "execute",
                "domain": "academy_ops",
                "tool": "academy_student_record_lookup",
                "confidence": 0.9,
                "intent": {"kind": "student_record_lookup"},
                "evidence": ["기록"],
                "args": {"student_query": "박서현"},
            }
        )

    def handler(*_: object, **__: object) -> str:
        return '{"ok": false, "message": "학생을 찾지 못했어. 이름이나 학교를 조금 더 정확히 알려줘."}'

    async def fake_copy(*, user_text: str, intent: str, fallback: str) -> str:
        assert user_text == "박서현 기록 보여줘"
        assert intent == "academy_student_record_lookup.not_ok"
        assert "학생을 찾지 못했어" in fallback
        return "지금 연결된 학원 기준으로는 박서현 학생을 찾지 못했어. 이름이나 학교를 조금 더 정확히 알려줘."

    monkeypatch.setattr("plugins.academy_ops.natural_router.naturalize_guidance_response", fake_copy)

    route = await resolve_and_execute_academy_request(
        "박서현 기록 보여줘",
        resolver=resolver,
        handlers={"academy_student_record_lookup": handler},
    )

    assert route == AcademyNaturalRoute.HANDLED
    assert route.response_text.startswith("지금 연결된 학원 기준")


def _response(payload: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))]
    )
