"""Tests for Peak daily plan lookup and fast model routing."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from types import SimpleNamespace

from gateway.config import Platform
from gateway.platforms.base import MessageEvent
from gateway.session import SessionSource
from plugins.academy_ops import _academy_command, _capture_gateway_context, register
from plugins.academy_ops.academy_query_tools import _plan_by_date_tool_handler
from plugins.academy_ops.auth_store import AcademyBinding, save_binding
from plugins.academy_ops.commentary_config import (
    COMMENTARY_ERROR_MESSAGE,
    COMMENTARY_EXTRA_BODY,
    COMMENTARY_FALLBACK_MODELS,
    COMMENTARY_MODEL,
    COMMENTARY_PROVIDER,
    COMMENTARY_TIMEOUT_MESSAGE,
)
from plugins.academy_ops.plan_commentary import (
    generate_plan_commentary,
    plan_commentary_facts,
    plan_commentary_messages,
    schedule_plan_commentary,
)
from plugins.academy_ops.plan_lookup import plan_lookup_for_day
from plugins.academy_ops.quick_router import classify_quick_operation, quick_command_for


class PlanClient:
    def get_peak_plans(self, day: date, *, time_slot: str = "") -> dict:
        assert day == date(2026, 5, 25)
        assert time_slot == ""
        return {
            "success": True,
            "date": "2026-05-25",
            "plans": [
                {
                    "id": 330,
                    "date": "2026-05-25",
                    "time_slot": "evening",
                    "instructor_id": 1,
                    "instructor_name": "박성준",
                    "updated_at": "2026-05-25 20:50:59",
                    "exercises": [
                        {"exercise_id": 344, "name": "20m왕복달리기", "note": "측정"},
                        {"exercise_id": 230, "name": "cc스쿼트", "note": ""},
                    ],
                    "completed_exercises": [344],
                },
                {
                    "id": 331,
                    "date": "2026-05-25",
                    "time_slot": "evening",
                    "instructor_name": "오철민",
                    "exercises": [],
                    "completed_exercises": [],
                },
            ],
        }


def test_plan_lookup_filters_trainer_and_marks_completion() -> None:
    result = plan_lookup_for_day(PlanClient(), date(2026, 5, 25), trainer_query="박성준")

    assert result["summary"] == {"plans": 1, "exercises": 2, "completed": 1}
    assert result["plans"][0]["instructor_name"] == "박성준"
    assert result["plans"][0]["exercises"][0]["completed"] is True
    assert result["plans"][0]["exercises"][1]["completed"] is False


def test_plan_tool_reads_structured_date_and_trainer_without_sensitive_fields() -> None:
    result = json.loads(
        _plan_by_date_tool_handler(
            {"date": "2026-05-25", "trainer_query": "박성준"},
            client=PlanClient(),
        )
    )

    assert result["ok"] is True
    assert result["operation"] == "plan.by_date"
    assert result["date"] == "2026-05-25"
    assert result["trainer_query"] == "박성준"
    assert result["plans"][0]["completed_count"] == 1
    dumped = json.dumps(result, ensure_ascii=False)
    assert "010-" not in dumped


def test_quick_router_does_not_rewrite_natural_plan_request() -> None:
    request = "2026-05-25 박성준 운동계획서좀 줘"

    assert classify_quick_operation(request) == ""
    assert quick_command_for(request) == ""


def test_gateway_context_routes_bound_plan_session_to_fast_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path))
    save_binding(
        AcademyBinding(
            discord_user_id="discord-user-1",
            user_id="1",
            email="owner@example.com",
            name="원장",
            role="owner",
            academy_id="2",
            academy_name="학원",
            token_ciphertext="ciphertext",
            created_at=1,
            updated_at=1,
        )
    )

    source = SessionSource(
        platform=Platform.DISCORD,
        user_id="discord-user-1",
        chat_id="channel-1",
        guild_id="guild-1",
    )

    class Gateway:
        def __init__(self) -> None:
            self._session_model_overrides = {}
            self.evicted = []

        def _session_key_for_source(self, source):
            return f"{source.platform.value}:{source.user_id}:{source.chat_id}"

        def _evict_cached_agent(self, session_key):
            self.evicted.append(session_key)

    gateway = Gateway()
    result = _capture_gateway_context(MessageEvent(text="2026-05-25 박성준 운동계획서좀 줘", source=source), gateway=gateway)

    assert result == {"action": "allow"}
    session_key = f"{Platform.DISCORD.value}:discord-user-1:channel-1"
    assert gateway._session_model_overrides[session_key] == {
        "model": COMMENTARY_MODEL,
        "provider": COMMENTARY_PROVIDER,
    }
    assert gateway.evicted == [session_key]


def test_academy_quick_command_is_disabled() -> None:
    output = _academy_command("quick plan.by_date 2026-05-25 박성준 운동계획서좀 줘")

    assert "빠른 문장 가로채기는 꺼져 있어" in output


def test_plan_commentary_prompt_uses_payload_without_category_rules() -> None:
    payload = json.loads(
        _plan_by_date_tool_handler(
            {"date": "2026-05-25", "trainer_query": "박성준"},
            client=PlanClient(),
        )
    )

    facts = plan_commentary_facts(payload)
    messages = plan_commentary_messages(facts)
    prompt_text = "\n".join(message["content"] for message in messages)

    assert facts["exercises"][0] == {"name": "20m왕복달리기", "note": "측정", "completed": True}
    assert "20m왕복달리기" in prompt_text
    assert "측정" in prompt_text
    assert "스피드" not in prompt_text
    assert "점프" not in prompt_text
    assert "근력" not in prompt_text


def test_registers_fast_commentary_auxiliary_defaults() -> None:
    class FakeContext:
        def __init__(self):
            self.aux_defaults = {}

        def register_command(self, *args, **kwargs):
            return None

        def register_hook(self, *args, **kwargs):
            return None

        def register_auxiliary_task(self, **kwargs):
            self.aux_defaults = kwargs["defaults"]

        def register_tool(self, **kwargs):
            return None

    ctx = FakeContext()

    register(ctx)

    assert ctx.aux_defaults["provider"] == COMMENTARY_PROVIDER
    assert ctx.aux_defaults["model"] == COMMENTARY_MODEL
    assert ctx.aux_defaults["timeout"] <= 10
    assert ctx.aux_defaults["extra_body"] == COMMENTARY_EXTRA_BODY


def test_generate_plan_commentary_falls_back_after_timeout(monkeypatch) -> None:
    calls = []

    class Choice:
        message = SimpleNamespace(content="폴백 모델 코멘트")

    class Response:
        choices = [Choice()]

    async def fake_async_call_llm(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"] == COMMENTARY_MODEL:
            raise TimeoutError("primary slow")
        return Response()

    monkeypatch.setattr("agent.auxiliary_client.async_call_llm", fake_async_call_llm)

    text = asyncio.run(generate_plan_commentary({"plans": [{"exercises": [{"name": "점프", "completed": True}]}]}))

    assert text == "폴백 모델 코멘트"
    assert calls[:2] == [COMMENTARY_MODEL, COMMENTARY_FALLBACK_MODELS[0]]


def test_schedule_plan_commentary_sends_followup_comment() -> None:
    sent = []

    class Adapter:
        async def send(self, chat_id, content, metadata=None):
            sent.append((chat_id, content, metadata))

    class Gateway:
        adapters = {"discord": Adapter()}

        def _thread_metadata_for_source(self, source, reply_to_message_id=None):
            return {"thread_id": source.thread_id, "reply": reply_to_message_id}

        def _reply_anchor_for_event(self, event):
            return "msg-1"

    async def fake_caller(payload):
        assert payload["plans"][0]["instructor_name"] == "박성준"
        return "운동명과 메모 기준으로 왕복달리기 측정 위주였어."

    async def run_case():
        source = SimpleNamespace(platform="discord", chat_id="thread-1", thread_id="thread-1")
        event = SimpleNamespace(source=source)
        payload = {
            "plans": [
                {
                    "instructor_name": "박성준",
                    "exercises": [{"name": "20m왕복달리기", "note": "측정", "completed": True}],
                }
            ]
        }
        assert schedule_plan_commentary(gateway=Gateway(), event=event, payload=payload, caller=fake_caller)
        await asyncio.sleep(0.01)

    asyncio.run(run_case())

    assert sent == [
        (
            "thread-1",
            "미호 코멘트: 운동명과 메모 기준으로 왕복달리기 측정 위주였어.",
            {"thread_id": "thread-1", "reply": "msg-1"},
        )
    ]


def test_schedule_plan_commentary_reports_timeout_notice() -> None:
    sent = []

    class Adapter:
        async def send(self, chat_id, content, metadata=None):
            sent.append((chat_id, content, metadata))

    class Gateway:
        adapters = {"discord": Adapter()}

        def _thread_metadata_for_source(self, source, reply_to_message_id=None):
            return {"thread_id": source.thread_id, "reply": reply_to_message_id}

        def _reply_anchor_for_event(self, event):
            return "msg-1"

    async def timeout_caller(payload):
        raise TimeoutError("slow commentary")

    async def run_case():
        source = SimpleNamespace(platform="discord", chat_id="thread-1", thread_id="thread-1")
        event = SimpleNamespace(source=source)
        payload = {"plans": [{"instructor_name": "박성준", "exercises": []}]}
        assert schedule_plan_commentary(gateway=Gateway(), event=event, payload=payload, caller=timeout_caller)
        await asyncio.sleep(0.01)

    asyncio.run(run_case())

    assert sent == [
        (
            "thread-1",
            COMMENTARY_TIMEOUT_MESSAGE,
            {"thread_id": "thread-1", "reply": "msg-1"},
        )
    ]


def test_schedule_plan_commentary_reports_error_notice() -> None:
    sent = []

    class Adapter:
        async def send(self, chat_id, content, metadata=None):
            sent.append((chat_id, content, metadata))

    class Gateway:
        adapters = {"discord": Adapter()}

        def _thread_metadata_for_source(self, source, reply_to_message_id=None):
            return {"thread_id": source.thread_id, "reply": reply_to_message_id}

        def _reply_anchor_for_event(self, event):
            return "msg-1"

    async def failing_caller(payload):
        raise RuntimeError("provider failed")

    async def run_case():
        source = SimpleNamespace(platform="discord", chat_id="thread-1", thread_id="thread-1")
        event = SimpleNamespace(source=source)
        payload = {"plans": [{"instructor_name": "박성준", "exercises": []}]}
        assert schedule_plan_commentary(gateway=Gateway(), event=event, payload=payload, caller=failing_caller)
        await asyncio.sleep(0.01)

    asyncio.run(run_case())

    assert sent == [
        (
            "thread-1",
            COMMENTARY_ERROR_MESSAGE,
            {"thread_id": "thread-1", "reply": "msg-1"},
        )
    ]
