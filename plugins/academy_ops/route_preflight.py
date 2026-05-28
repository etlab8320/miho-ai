"""High-confidence academy request preflight routing."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any


IMAGE_MARKERS = ("이미지", "사진", "png", "달력", "캘린더", "카드")
ATTENDANCE_MARKERS = ("출석", "결석", "지각", "미체크")
TRIAL_ALIASES = ("체험수업", "무료체험", "체험상담", "trial", "trial lesson")
DATE_ALIASES = ("오늘", "금일", "내일", "어제", "이번주", "저번주", "지난주", "이번달", "이번 달", "저번달", "지난달")
STAFF_MARKERS = ("강사", "선생")
STAFF_ATTENDANCE_INTENT_MARKERS = ("누구출근", "누가출근", "출근한", "출근했", "출근기록", "출근자")
STAFF_FUTURE_MARKERS = ("예정", "해야", "배정")
STAFF_RANGE_MARKERS = ("총", "몇번", "몇회", "횟수", "일정", "기록")
STAFF_STOPWORDS = (
    "강사",
    "선생님",
    "선생",
    "출근",
    "일정",
    "기록",
    "조회",
    "총",
    "몇번",
    "몇",
    "번",
    "회",
    "횟수",
    "했어",
    "했니",
    "했나",
    "줘",
    "좀",
    "그럼",
)
ATTENDANCE_STOPWORDS = (
    "출석",
    "결석",
    "지각",
    "미체크",
    "조회",
    "정리",
    "일자별",
    "날짜별",
    "이미지",
    "사진",
    "달력",
    "캘린더",
    "카드",
    "좀",
    "줘",
    "해줘",
    "해봐",
    "해주라",
    "해주셈",
    "주셈",
    "봐",
    "부탁",
    "월",
    "이번",
    "저번",
    "지난",
    "달",
    "주",
    "로",
)


def academy_preflight_decision(
    text: str,
    today: str,
    thread_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    normalized = _compact_text(text)
    trial = _trial_schedule_decision(normalized, today)
    if trial is not None:
        return trial
    staff = _staff_attendance_decision(text, normalized, today, thread_context or {})
    if staff is not None:
        return staff
    return _student_attendance_decision(text, normalized, today)


def _trial_schedule_decision(normalized: str, today: str) -> dict[str, Any] | None:
    day = _single_day_from_alias(normalized, today)
    if not day or not _contains_any(normalized, TRIAL_ALIASES):
        return None
    return {
        "action": "execute",
        "tool": "academy_consultation_schedule_range",
        "args": {
            "start_date": day,
            "end_date": day,
            "new_registration_only": False,
            "trial_only": True,
        },
        "confidence": 0.99,
    }


def _student_attendance_decision(text: str, normalized: str, today: str) -> dict[str, Any] | None:
    if not _contains_any(normalized, ATTENDANCE_MARKERS):
        return None
    resolved_range = _date_range_from_text(normalized, today)
    if resolved_range is None:
        return None
    student_query = _student_query_from_text(text)
    if not student_query:
        return None
    tool = (
        "academy_student_attendance_calendar_image"
        if _contains_any(normalized, IMAGE_MARKERS)
        else "academy_student_attendance_range"
    )
    return {
        "action": "execute",
        "tool": tool,
        "args": {
            "student_query": student_query,
            "start_date": resolved_range[0],
            "end_date": resolved_range[1],
            "today": today[:10],
        },
        "response_focus": "summary",
        "confidence": 0.98,
    }


def _staff_attendance_decision(
    text: str,
    normalized: str,
    today: str,
    thread_context: dict[str, Any],
) -> dict[str, Any] | None:
    if "출근" not in normalized or not _is_staff_attendance_intent(normalized, thread_context):
        return None
    if _contains_any(normalized, STAFF_FUTURE_MARKERS) and _single_day_from_alias(normalized, today) > today[:10]:
        return None
    resolved_range = _date_range_from_text(normalized, today)
    if resolved_range is None:
        return None
    staff_query = _staff_query_from_text(text) or _staff_query_from_context(thread_context)
    is_single_day = resolved_range[0] == resolved_range[1]
    if is_single_day and not staff_query and not _contains_any(normalized, STAFF_RANGE_MARKERS):
        return {
            "action": "execute",
            "tool": "academy_staff_attendance_day",
            "args": {"date": resolved_range[0]},
            "skip_synthesis": True,
            "confidence": 0.98,
        }
    if not staff_query:
        return None
    return {
        "action": "execute",
        "tool": "academy_staff_attendance_range",
        "args": {
            "staff_query": staff_query,
            "start_date": resolved_range[0],
            "end_date": resolved_range[1],
        },
        "skip_synthesis": True,
        "confidence": 0.98,
    }


def _is_staff_attendance_intent(normalized: str, thread_context: dict[str, Any]) -> bool:
    if _contains_any(normalized, STAFF_MARKERS):
        return True
    if _staff_query_from_context(thread_context):
        return _contains_any(normalized, STAFF_RANGE_MARKERS + DATE_ALIASES)
    return _contains_any(normalized, STAFF_ATTENDANCE_INTENT_MARKERS)


def _date_range_from_text(normalized: str, today: str) -> tuple[str, str] | None:
    base = _today_date(today)
    month = _month_number_before_wol(normalized)
    if month is not None:
        last_day = monthrange(base.year, month)[1]
        return date(base.year, month, 1).isoformat(), date(base.year, month, last_day).isoformat()
    if "이번달" in normalized:
        last_day = monthrange(base.year, base.month)[1]
        return date(base.year, base.month, 1).isoformat(), date(base.year, base.month, last_day).isoformat()
    if "저번달" in normalized or "지난달" in normalized:
        first = date(base.year, base.month, 1) - timedelta(days=1)
        return date(first.year, first.month, 1).isoformat(), first.isoformat()
    if "저번주" in normalized or "지난주" in normalized:
        start = base - timedelta(days=base.weekday() + 7)
        return start.isoformat(), (start + timedelta(days=6)).isoformat()
    if "이번주" in normalized:
        start = base - timedelta(days=base.weekday())
        return start.isoformat(), (start + timedelta(days=6)).isoformat()
    day = _single_day_from_alias(normalized, today)
    return (day, day) if day else None


def _month_number_before_wol(normalized: str) -> int | None:
    for index, char in enumerate(normalized):
        if char != "월":
            continue
        start = index
        while start > 0 and normalized[start - 1].isdigit():
            start -= 1
        if start == index:
            continue
        month = _to_int(normalized[start:index])
        if 1 <= month <= 12:
            return month
    return None


def _student_query_from_text(text: str) -> str:
    cleaned = _remove_month_tokens(str(text or ""))
    for token in DATE_ALIASES + ATTENDANCE_STOPWORDS + IMAGE_MARKERS:
        cleaned = cleaned.replace(token, " ")
    words = [word.strip(" .,!?~!ㅋㅎ") for word in cleaned.split()]
    candidates = [word for word in words if word]
    return candidates[0] if len(candidates) == 1 else ""


def _staff_query_from_text(text: str) -> str:
    cleaned = _remove_month_tokens(str(text or ""))
    for token in DATE_ALIASES + STAFF_STOPWORDS:
        cleaned = cleaned.replace(token, " ")
    words = [word.strip(" .,!?~!ㅋㅎ") for word in cleaned.split()]
    candidates = [word for word in words if word]
    return candidates[0] if len(candidates) == 1 else ""


def _staff_query_from_context(thread_context: dict[str, Any]) -> str:
    if thread_context.get("kind") != "staff":
        return ""
    return str(thread_context.get("staff_query") or "").strip()


def _remove_month_tokens(text: str) -> str:
    chars = list(text)
    for index, char in enumerate(chars):
        if char != "월":
            continue
        start = index
        while start > 0 and chars[start - 1].isdigit():
            start -= 1
        if start == index:
            continue
        for pos in range(start, index + 1):
            chars[pos] = " "
    return "".join(chars)


def _single_day_from_alias(normalized_text: str, today: str) -> str:
    base = _today_date(today)
    for alias, offset in (("오늘", 0), ("금일", 0), ("내일", 1), ("어제", -1)):
        if alias in normalized_text:
            return (base + timedelta(days=offset)).isoformat()
    return ""


def _today_date(today: str) -> date:
    try:
        return datetime.fromisoformat(today[:10]).date()
    except ValueError:
        return date.today()


def _compact_text(text: str) -> str:
    return "".join(str(text or "").lower().split())


def _contains_any(text: str, aliases: tuple[str, ...]) -> bool:
    return any(_compact_text(alias) in text for alias in aliases if alias)


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
