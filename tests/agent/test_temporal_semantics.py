from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agent.temporal_semantics import build_temporal_reference, format_temporal_context


def test_after_midnight_reference_exposes_current_and_previous_dates() -> None:
    ref = build_temporal_reference(datetime(2026, 5, 29, 0, 30, tzinfo=ZoneInfo("Asia/Seoul")))

    assert ref.calendar_date == "2026-05-29"
    assert ref.previous_calendar_date == "2026-05-28"
    assert ref.is_after_midnight_window is True


def test_after_midnight_window_resets_at_configured_hour() -> None:
    ref = build_temporal_reference(datetime(2026, 5, 29, 4, 0, tzinfo=ZoneInfo("Asia/Seoul")))

    assert ref.calendar_date == "2026-05-29"
    assert ref.previous_calendar_date == "2026-05-28"
    assert ref.is_after_midnight_window is False


def test_temporal_context_contains_only_neutral_time_facts() -> None:
    ref = build_temporal_reference(datetime(2026, 5, 29, 1, 5, tzinfo=ZoneInfo("Asia/Seoul")))

    context = format_temporal_context(ref)

    assert "calendar_date=2026-05-29" in context
    assert "previous_calendar_date=2026-05-28" in context
    assert "after_midnight_window=true" in context
    assert "오늘" not in context
