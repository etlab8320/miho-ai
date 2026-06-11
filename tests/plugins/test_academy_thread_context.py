"""Tests for SQLite-backed academy thread context (T7).

Covers:
- roundtrip per context kind (student / monthly_test / pending_request)
- key isolation (key A saved → key B returns empty)
- restart survival (dict cleared → SQLite restores)
- TTL expiry (expired row deleted, empty result returned)

All tests use tmp_path + monkeypatch to override the DB path so ~/.miho is
never touched.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import plugins.academy_ops.thread_context as tc


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Point every test at a fresh DB in tmp_path and clear the dict cache."""
    db = tmp_path / "thread_context.sqlite3"
    monkeypatch.setattr(tc, "_DB_PATH_OVERRIDE", db)
    tc._CONTEXTS.clear()
    yield
    tc._CONTEXTS.clear()
    monkeypatch.setattr(tc, "_DB_PATH_OVERRIDE", None)


# ---------------------------------------------------------------------------
# Roundtrip tests
# ---------------------------------------------------------------------------

def test_student_context_roundtrip():
    key = "test:student"
    tc.remember_thread_context(
        key,
        tool_name="academy_student_attendance_calendar_image",
        args={"student_query": "김민준", "today": "2026-06-01"},
        payload={"ok": True, "student": {"name": "김민준"}},
    )
    ctx = tc.get_thread_context(key)
    assert ctx["kind"] == "student"
    assert ctx["student_query"] == "김민준"
    assert ctx["tool"] == "academy_student_attendance_calendar_image"


def test_monthly_test_context_roundtrip():
    key = "test:monthly"
    participants = [{"name": "박서연", "gender": "F", "school": "A고", "records": []}]
    tc.remember_thread_context(
        key,
        tool_name="academy_monthly_test_records",
        args={"event_query": "윗몸일으키기", "test_month": "2026-05"},
        payload={
            "ok": True,
            "test": {"id": 7, "test_month": "2026-05"},
            "participants": participants,
            "record_types": [{"id": 1, "name": "윗몸일으키기", "unit": "회"}],
        },
    )
    ctx = tc.get_thread_context(key)
    assert ctx["kind"] == "monthly_test"
    assert ctx["test_id"] == 7
    assert ctx["test_month"] == "2026-05"
    assert isinstance(ctx["participants"], list)
    assert ctx["participants"][0]["name"] == "박서연"


def test_pending_request_roundtrip():
    key = "test:pending"
    tc.remember_pending_request(
        key,
        tool_name="academy_student_attendance_range",
        args={"student_query": "이서준"},
        request_text="서준이 5월 출석 알려줘",
        reason="start_date 없음",
    )
    ctx = tc.get_thread_context(key)
    assert ctx["kind"] == "pending_request"
    assert ctx["request_text"] == "서준이 5월 출석 알려줘"
    assert ctx["args"]["student_query"] == "이서준"


# ---------------------------------------------------------------------------
# Key isolation
# ---------------------------------------------------------------------------

def test_key_isolation():
    key_a = "guild:1:chan:1"
    key_b = "guild:1:chan:2"
    tc.remember_thread_context(
        key_a,
        tool_name="academy_student_attendance_calendar_image",
        args={"student_query": "홍길동"},
        payload={"ok": True, "student": {"name": "홍길동"}},
    )
    ctx_b = tc.get_thread_context(key_b)
    assert ctx_b == {}


# ---------------------------------------------------------------------------
# Restart survival — dict cleared, SQLite restores
# ---------------------------------------------------------------------------

def test_restart_survival():
    key = "test:restart"
    tc.remember_thread_context(
        key,
        tool_name="academy_staff_attendance_range",
        args={"staff_query": "김코치", "start_date": "2026-05-01", "end_date": "2026-05-31"},
        payload={"ok": True},
    )
    # Simulate process restart by wiping the in-memory dict.
    tc._CONTEXTS.clear()

    ctx = tc.get_thread_context(key)
    assert ctx["kind"] == "staff"
    assert ctx["staff_query"] == "김코치"


# ---------------------------------------------------------------------------
# TTL expiry
# ---------------------------------------------------------------------------

def test_ttl_expired_returns_empty_and_deletes_row(tmp_path):
    db = tc._get_db_path()
    key = "test:expired"

    # Write a context via normal path first so schema is ready.
    tc.remember_thread_context(
        key,
        tool_name="academy_student_attendance_calendar_image",
        args={"student_query": "최예린"},
        payload={"ok": True, "student": {"name": "최예린"}},
    )
    # Manually backdate expires_at to the past.
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat()
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE thread_context SET expires_at = ? WHERE key = ?", (past, key))

    # Also clear dict cache so the read goes to SQLite.
    tc._CONTEXTS.clear()

    ctx = tc.get_thread_context(key)
    assert ctx == {}

    # Row must be gone from DB.
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT 1 FROM thread_context WHERE key = ?", (key,)).fetchone()
    assert row is None


# ---------------------------------------------------------------------------
# pop_pending_request removes from both dict and DB
# ---------------------------------------------------------------------------

def test_pop_pending_request_clears_db():
    key = "test:pop"
    tc.remember_pending_request(
        key,
        tool_name="academy_student_attendance_range",
        args={"student_query": "정하은"},
        request_text="하은이 6월 출석 알려줘",
        reason="날짜 미지정",
    )
    popped = tc.pop_pending_request(key)
    assert popped["kind"] == "pending_request"

    # Both dict and DB should be empty now.
    assert key not in tc._CONTEXTS
    db = tc._get_db_path()
    with sqlite3.connect(db) as conn:
        row = conn.execute("SELECT 1 FROM thread_context WHERE key = ?", (key,)).fetchone()
    assert row is None


# ---------------------------------------------------------------------------
# clear_thread_contexts wipes dict and DB
# ---------------------------------------------------------------------------

def test_clear_wipes_db():
    for i in range(3):
        tc.remember_thread_context(
            f"key:{i}",
            tool_name="academy_student_attendance_calendar_image",
            args={"student_query": f"학생{i}"},
            payload={"ok": True, "student": {"name": f"학생{i}"}},
        )

    tc.clear_thread_contexts()

    assert tc._CONTEXTS == {}
    db = tc._get_db_path()
    with sqlite3.connect(db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM thread_context").fetchone()[0]
    assert count == 0


# ---------------------------------------------------------------------------
# Non-ok payload is not stored
# ---------------------------------------------------------------------------

def test_failed_payload_not_stored():
    key = "test:fail"
    tc.remember_thread_context(
        key,
        tool_name="academy_student_attendance_calendar_image",
        args={"student_query": "홍길동"},
        payload={"ok": False},
    )
    assert tc.get_thread_context(key) == {}
