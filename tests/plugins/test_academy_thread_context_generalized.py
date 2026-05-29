"""Generalized thread-context inheritance for academy follow-up questions.

Context inheritance used to fire only for 7 whitelisted tools, so a follow-up
after e.g. a record lookup ('그 학생 다른 종목은?') lost its subject. It is now
generalized over TOOL_CONTRACTS: any tool inherits the entity args it declares.
Tools that carry no entity must not wipe the active subject.
"""

from __future__ import annotations

import pytest

from plugins.academy_ops import thread_context as tc
from plugins.academy_ops.natural_router import _resolved_args


@pytest.fixture(autouse=True)
def _clear():
    tc.clear_thread_contexts()
    yield
    tc.clear_thread_contexts()


def test_record_lookup_followup_inherits_subject_and_event():
    key = "k"
    # record_lookup is NOT in the legacy whitelist; it must still leave context.
    tc.remember_thread_context(
        key,
        tool_name="academy_student_record_lookup",
        args={"student_query": "서하", "event_query": "윗몸일으키기"},
        payload={"ok": True},
    )
    ctx = tc.get_thread_context(key)
    assert ctx.get("student_query") == "서하"

    # Follow-up omits the student but names a new event -> subject carries over,
    # the explicitly given event is kept.
    resolved = _resolved_args(
        "academy_student_record_lookup", {"event_query": "메디신볼"}, key
    )
    assert resolved["student_query"] == "서하"
    assert resolved["event_query"] == "메디신볼"


def test_entityless_tool_does_not_wipe_active_subject():
    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_student_record_lookup",
        args={"student_query": "서하"},
        payload={"ok": True},
    )
    # A whole-day attendance lookup carries no inheritable entity.
    tc.remember_thread_context(
        key,
        tool_name="academy_attendance_day",
        args={"date": "2026-05-30"},
        payload={"ok": True},
    )
    assert tc.get_thread_context(key).get("student_query") == "서하"


def test_subject_not_inherited_when_explicitly_changed():
    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_student_record_lookup",
        args={"student_query": "서하"},
        payload={"ok": True},
    )
    resolved = _resolved_args(
        "academy_student_record_lookup", {"student_query": "민준"}, key
    )
    assert resolved["student_query"] == "민준"


def test_monthly_test_context_inheritance_preserved():
    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_monthly_test_records",
        args={"event_query": "윗몸일으키기", "test_month": "2026-05"},
        payload={"ok": True, "test": {"id": 13, "test_month": "2026-05"}},
    )
    resolved = _resolved_args("academy_monthly_test_records", {}, key)
    assert resolved["event_query"] == "윗몸일으키기"
    assert resolved["test_id"] == 13


def test_staff_query_inheritance_preserved():
    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_staff_attendance_range",
        args={"staff_query": "김코치", "start_date": "2026-05-01", "end_date": "2026-05-31"},
        payload={"ok": True},
    )
    resolved = _resolved_args("academy_staff_attendance_range", {}, key)
    assert resolved["staff_query"] == "김코치"
    assert resolved["start_date"] == "2026-05-01"


def test_subjectless_schedule_does_not_inherit_student_dates():
    # A whole-academy schedule query has no entity arg; it must NOT pick up a
    # prior student's date window.
    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_student_attendance_range",
        args={"student_query": "서하", "start_date": "2026-05-25", "end_date": "2026-05-31"},
        payload={"ok": True},
    )
    resolved = _resolved_args("academy_schedule_range", {}, key)
    assert not resolved.get("start_date")
    assert not resolved.get("end_date")


def test_student_range_still_inherits_dates():
    # Subject-scoped range query keeps the prior date window (preserved behaviour).
    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_student_attendance_range",
        args={"student_query": "서하", "start_date": "2026-05-25", "end_date": "2026-05-31"},
        payload={"ok": True},
    )
    resolved = _resolved_args("academy_student_attendance_range", {"student_query": "민준"}, key)
    assert resolved["start_date"] == "2026-05-25"
    assert resolved["end_date"] == "2026-05-31"


def test_cross_subject_args_do_not_leak():
    # A staff subject must never fill a student_query slot (key names gate it).
    key = "k"
    tc.remember_thread_context(
        key,
        tool_name="academy_staff_attendance_range",
        args={"staff_query": "김코치"},
        payload={"ok": True},
    )
    resolved = _resolved_args("academy_student_record_lookup", {}, key)
    assert not resolved.get("student_query")
