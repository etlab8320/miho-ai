"""Context handoff from academy router to the body agent.

The real failure: a HANDLED academy reply (e.g. "월말테스트 전체종목 표") is never
written to the transcript, so a follow-up like "최혜은 기록만" that falls through to
ALLOW reaches the body agent with ZERO knowledge of the previous turn — it then
picks the wrong tool and answers "기록 없음".

Fixes under test:
1. An all-events monthly test (no event_query) still leaves thread context so a
   follow-up can inherit the test.
2. format_context_note() renders the prior turn as a body-agent note — with a
   self-check instruction — and bakes in NO student/school/event names (product).
3. _inject_prior_context() puts that note on event.channel_prompt on ALLOW only.
"""

from __future__ import annotations

import pytest

from plugins.academy_ops import thread_context as tc
from plugins.academy_ops import _inject_prior_context, _persist_handled_turn


@pytest.fixture(autouse=True)
def _clear():
    tc.clear_thread_contexts()
    yield
    tc.clear_thread_contexts()


def test_all_events_remembers_context_without_event_query():
    # "전체종목 표" carries no event_query, but identifies a test -> must persist.
    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_monthly_test_records",
        args={},  # no event_query
        payload={"ok": True, "test": {"id": 13, "test_month": "2026-05"}},
    )
    ctx = tc.get_thread_context(key)
    assert ctx.get("kind") == "monthly_test"
    assert ctx.get("test_id") == 13
    assert ctx.get("test_month") == "2026-05"


def test_unidentified_monthly_test_does_not_persist():
    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_monthly_test_records",
        args={},
        payload={"ok": True, "test": {}},  # no id, no month, no event
    )
    assert tc.get_thread_context(key) == {}


def test_format_context_note_monthly_test_has_self_check_and_handoff():
    note = tc.format_context_note(
        {"kind": "monthly_test", "tool": "academy_monthly_test_records",
         "test_month": "2026-05", "test_id": 13}
    )
    assert "월말 테스트" in note
    assert "검수" in note          # self-check instruction present
    assert "직전" in note          # context-handoff instruction present
    assert "academy_monthly_test_records" in note  # tool hint is a runtime value


def test_format_context_note_uses_only_runtime_values_no_hardcoded_names():
    # The function must never bake in a specific student/school/event name.
    note = tc.format_context_note(
        {"kind": "student", "tool": "academy_student_card_image", "student_query": "RUNTIME_NAME"}
    )
    assert "RUNTIME_NAME" in note  # echoes the runtime value, not a literal
    blank = tc.format_context_note({"kind": "student", "tool": "x", "student_query": ""})
    assert "RUNTIME_NAME" not in blank


def test_format_context_note_blank_for_no_context():
    assert tc.format_context_note({}) == ""
    assert tc.format_context_note({"kind": "pending_request"}) == ""
    assert tc.format_context_note({"kind": "generic", "tool": "x"}) == ""  # no entity


class _Event:
    def __init__(self):
        self.channel_prompt = None


def test_inject_prior_context_sets_channel_prompt_when_context_exists():
    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_monthly_test_records",
        args={},
        payload={"ok": True, "test": {"id": 13, "test_month": "2026-05"}},
    )
    ev = _Event()
    _inject_prior_context(ev, key)
    assert ev.channel_prompt and "월말 테스트" in ev.channel_prompt


def test_inject_prior_context_noop_without_context():
    ev = _Event()
    _inject_prior_context(ev, "missing-key")
    assert ev.channel_prompt is None


def test_inject_prior_context_preserves_existing_channel_prompt():
    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_monthly_test_records",
        args={},
        payload={"ok": True, "test": {"id": 13, "test_month": "2026-05"}},
    )
    ev = _Event()
    ev.channel_prompt = "EXISTING"
    _inject_prior_context(ev, key)
    assert ev.channel_prompt.startswith("EXISTING")
    assert "월말 테스트" in ev.channel_prompt


# --- Roster handoff: the body agent never saw the HANDLED payload, so the
# remembered roster must ride into its context next turn (no re-fetch). ---

ROSTER_PAYLOAD = {
    "ok": True,
    "test": {"id": 13, "test_month": "2026-05"},
    "record_types": [{"record_type_id": "1", "name": "제자리멀리뛰기", "unit": "cm"}],
    "participants": [
        {"name": "RUNTIME_A", "gender": "M", "school": "X고", "records": {"1": 295}},
        {"name": "RUNTIME_B", "gender": "F", "school": "Y고", "records": {"1": 230}},
    ],
}


def test_monthly_test_remembers_roster():
    key = "k"
    tc.remember_thread_context(
        key, tool_name="academy_monthly_test_records", args={}, payload=ROSTER_PAYLOAD
    )
    ctx = tc.get_thread_context(key)
    assert isinstance(ctx.get("participants"), list) and len(ctx["participants"]) == 2
    assert isinstance(ctx.get("record_types"), list)


def test_note_inlines_roster_for_followup_filtering():
    key = "k"
    tc.remember_thread_context(
        key, tool_name="academy_monthly_test_records", args={}, payload=ROSTER_PAYLOAD
    )
    note = tc.format_context_note(tc.get_thread_context(key))
    assert "RUNTIME_A" in note and "RUNTIME_B" in note  # actual records reach the agent
    assert "제자리멀리뛰기" in note                       # event definitions included
    assert "다시 조회하지" in note                         # speed: filter, don't re-fetch
    assert "검수" in note                                  # self-check still present


def test_inject_carries_roster_to_channel_prompt():
    key = "k"
    tc.remember_thread_context(
        key, tool_name="academy_monthly_test_records", args={}, payload=ROSTER_PAYLOAD
    )
    ev = _Event()
    _inject_prior_context(ev, key)
    assert "RUNTIME_A" in ev.channel_prompt


def test_roster_inline_capped_for_large_tests():
    key = "k"
    big = [{"name": f"P{i}", "gender": "M", "school": "X", "records": {"1": i}} for i in range(120)]
    tc.remember_thread_context(
        key,
        tool_name="academy_monthly_test_records",
        args={},
        payload={
            "ok": True,
            "test": {"id": 1, "test_month": "2026-05"},
            "record_types": [{"record_type_id": "1", "name": "달리기", "unit": "초"}],
            "participants": big,
        },
    )
    note = tc.format_context_note(tc.get_thread_context(key))
    assert '"P0"' in note and '"P79"' in note    # first 80 inlined
    assert '"P119"' not in note                   # capped
    assert "다시 조회" in note                     # told how to get the rest


# --- HANDLED-turn persistence: a dispatch-shortcut reply must land in the
# transcript so the body agent sees it as recent history next turn. ---


class _Src:
    pass


class _Ev:
    def __init__(self):
        self.source = _Src()
        self.text = "Q"


class _Entry:
    session_id = "sid-1"


class _Store:
    def __init__(self):
        self.appended = []

    def get_or_create_session(self, source):
        return _Entry()

    def append_to_transcript(self, session_id, message):
        self.appended.append((session_id, message))


def test_persist_handled_turn_writes_question_and_answer():
    store = _Store()
    _persist_handled_turn(store, _Ev(), "어제 월말테스트 표", "종목별 기록 표야. MEDIA:/x.png")
    assert len(store.appended) == 2
    assert store.appended[0][1]["role"] == "user"
    assert store.appended[0][1]["content"] == "어제 월말테스트 표"
    assert store.appended[1][1]["role"] == "assistant"
    assert "표야" in store.appended[1][1]["content"]
    assert store.appended[0][0] == "sid-1"


def test_persist_handled_turn_noop_without_store_or_answer():
    # Must never raise — a transcript write can't be allowed to break the reply.
    _persist_handled_turn(None, _Ev(), "Q", "A")
    store = _Store()
    _persist_handled_turn(store, _Ev(), "Q", "")  # blank answer
    assert store.appended == []
