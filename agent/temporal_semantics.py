"""Shared relative-date semantics for local conversations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


DEFAULT_TIMEZONE = "Asia/Seoul"
DEFAULT_AMBIGUOUS_UNTIL_HOUR = 4


@dataclass(frozen=True)
class TemporalReference:
    calendar_date: str
    previous_calendar_date: str
    local_time: str
    timezone: str
    is_after_midnight_window: bool


def build_temporal_reference(
    timestamp: Any = None,
    *,
    timezone_name: str = DEFAULT_TIMEZONE,
    ambiguous_until_hour: int = DEFAULT_AMBIGUOUS_UNTIL_HOUR,
) -> TemporalReference:
    tz = ZoneInfo(timezone_name)
    local_dt = _coerce_datetime(timestamp, tz)
    local_date = local_dt.date()
    previous_date = local_date - timedelta(days=1)
    return TemporalReference(
        calendar_date=local_date.isoformat(),
        previous_calendar_date=previous_date.isoformat(),
        local_time=local_dt.strftime("%H:%M"),
        timezone=timezone_name,
        is_after_midnight_window=local_dt.hour < ambiguous_until_hour,
    )


def format_temporal_context(ref: TemporalReference) -> str:
    return (
        f"Turn time: calendar_date={ref.calendar_date}, "
        f"previous_calendar_date={ref.previous_calendar_date}, "
        f"local_time={ref.local_time}, timezone={ref.timezone}, "
        f"after_midnight_window={str(ref.is_after_midnight_window).lower()}."
    )


def _coerce_datetime(value: Any, tz: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif value:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(tz)
    else:
        dt = datetime.now(tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(tz)
