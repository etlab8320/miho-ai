"""Short-lived thread context for follow-up academy requests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any


STUDENT_CONTEXT_TOOLS = {
    "academy_student_attendance_calendar_image",
    "academy_student_attendance_range",
    "academy_student_summary",
    "academy_student_card_image",
    "academy_student_context",
}
STAFF_CONTEXT_TOOLS = {
    "academy_staff_attendance_range",
}
MONTHLY_TEST_CONTEXT_TOOLS = {
    "academy_monthly_test_records",
}
ASSIGNMENT_CONTEXT_TOOLS = {
    "academy_assignment_by_date",
}
# Entity args a follow-up question naturally inherits when left unspecified
# ("그 학생", "여자 평균은?"): the subject carries over from the last turn. The
# key name encodes meaning, so inheritance only fires between tools that share
# the arg — student_query never leaks into a staff query, etc. Relative dates
# are intentionally excluded (carrying "오늘" into "내일은?" would be wrong);
# only student-range periods carry over, preserving prior behaviour.
INHERITABLE_ENTITY_ARGS = (
    "student_query",
    "staff_query",
    "event_query",
    "trainer_query",
)
CONTEXT_TTL = timedelta(minutes=30)
_CONTEXTS: dict[str, dict[str, Any]] = {}


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    return not str(value).strip()


def academy_context_key(event: Any) -> str:
    source = getattr(event, "source", None)
    platform = str(getattr(getattr(source, "platform", None), "value", "") or "")
    parts = [
        platform,
        str(getattr(source, "guild_id", "") or ""),
        str(getattr(source, "chat_id", "") or ""),
        str(getattr(source, "thread_id", "") or ""),
        str(getattr(source, "user_id", "") or ""),
    ]
    return ":".join(parts)


def get_thread_context(key: str | None) -> dict[str, Any]:
    if not key:
        return {}
    item = _CONTEXTS.get(key)
    if not item:
        return {}
    updated_at = item.get("updated_at")
    if not isinstance(updated_at, datetime) or datetime.now(timezone.utc) - updated_at > CONTEXT_TTL:
        _CONTEXTS.pop(key, None)
        return {}
    return {name: value for name, value in item.items() if name != "updated_at"}


def remember_thread_context(
    key: str | None,
    *,
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    if not key or not payload.get("ok"):
        return
    if tool_name in MONTHLY_TEST_CONTEXT_TOOLS:
        _remember_monthly_test_context(key, tool_name=tool_name, args=args, payload=payload)
        return
    if tool_name in ASSIGNMENT_CONTEXT_TOOLS:
        _remember_assignment_context(key, tool_name=tool_name, args=args, payload=payload)
        return
    if tool_name in STAFF_CONTEXT_TOOLS:
        _remember_staff_context(key, tool_name=tool_name, args=args, payload=payload)
        return
    if tool_name in STUDENT_CONTEXT_TOOLS:
        _remember_student_context(key, tool_name=tool_name, args=args, payload=payload)
        return
    _remember_generic_context(key, tool_name=tool_name, args=args)


def _remember_student_context(
    key: str,
    *,
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    student = payload.get("student") if isinstance(payload.get("student"), dict) else {}
    card = payload.get("card") if isinstance(payload.get("card"), dict) else {}
    profile = card.get("profile") if isinstance(card.get("profile"), dict) else {}
    student_query = str(args.get("student_query") or student.get("name") or profile.get("name") or "").strip()
    if not student_query:
        return
    _CONTEXTS[key] = {
        "kind": "student",
        "tool": tool_name,
        "student_query": student_query,
        "start_date": str(payload.get("start_date") or args.get("start_date") or ""),
        "end_date": str(payload.get("end_date") or args.get("end_date") or ""),
        "today": str(args.get("today") or ""),
        "period_days": args.get("period_days"),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "updated_at": datetime.now(timezone.utc),
    }


def _remember_generic_context(key: str, *, tool_name: str, args: dict[str, Any]) -> None:
    """Remember entity args from any other successful tool so follow-ups can
    inherit them (e.g. record-lookup → '여자 평균은?'). Tools that carry no
    inheritable entity (e.g. a whole-day attendance lookup) leave the existing
    context untouched, so an unrelated turn never wipes the active subject.
    """
    entities = {
        name: str(args.get(name)).strip()
        for name in INHERITABLE_ENTITY_ARGS
        if not _is_blank(args.get(name))
    }
    if not entities:
        return
    record: dict[str, Any] = {
        "kind": "generic",
        "tool": tool_name,
        "updated_at": datetime.now(timezone.utc),
    }
    record.update(entities)
    for date_key in ("start_date", "end_date"):
        if not _is_blank(args.get(date_key)):
            record[date_key] = str(args[date_key]).strip()
    _CONTEXTS[key] = record


def _remember_monthly_test_context(
    key: str,
    *,
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    event_query = str(args.get("event_query") or "").strip()
    test = payload.get("test") if isinstance(payload.get("test"), dict) else {}
    test_id = test.get("id")
    test_month = str(test.get("test_month") or args.get("test_month") or "").strip()
    # event_query 없이 전체 종목을 본 경우(전체종목 표)에도, 어떤 월말 테스트였는지
    # 식별자가 있으면 맥락을 남긴다 → 후속 "특정 학생만/특정 종목만"이 그 테스트로 이어짐.
    if not event_query and test_id is None and not test_month:
        return
    _CONTEXTS[key] = {
        "kind": "monthly_test",
        "tool": tool_name,
        "event_query": event_query,
        "test_id": test_id,
        "test_month": test_month,
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        # Keep the actual roster the tool just fetched so a follow-up
        # ("그 학생만") can be answered from this remembered data — the body
        # agent never saw the HANDLED payload, so we hand it back next turn.
        "record_types": payload.get("record_types") if isinstance(payload.get("record_types"), list) else None,
        "participants": payload.get("participants") if isinstance(payload.get("participants"), list) else None,
        "updated_at": datetime.now(timezone.utc),
    }


def _remember_staff_context(
    key: str,
    *,
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    staff_query = str(args.get("staff_query") or payload.get("staff_query") or "").strip()
    instructors = payload.get("instructors") if isinstance(payload.get("instructors"), list) else []
    if not staff_query and len(instructors) == 1 and isinstance(instructors[0], dict):
        staff_query = str(instructors[0].get("name") or "").strip()
    if not staff_query:
        return
    _CONTEXTS[key] = {
        "kind": "staff",
        "tool": tool_name,
        "staff_query": staff_query,
        "start_date": str(payload.get("start_date") or args.get("start_date") or ""),
        "end_date": str(payload.get("end_date") or args.get("end_date") or ""),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "updated_at": datetime.now(timezone.utc),
    }


def _remember_assignment_context(
    key: str,
    *,
    tool_name: str,
    args: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
    if not slots:
        return
    _CONTEXTS[key] = {
        "kind": "assignment",
        "tool": tool_name,
        "date": str(payload.get("date") or args.get("date") or ""),
        "time_slot": str(payload.get("time_slot") or args.get("time_slot") or ""),
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "slots": slots,
        "updated_at": datetime.now(timezone.utc),
    }


def remember_pending_request(
    key: str | None,
    *,
    tool_name: str,
    args: dict[str, Any],
    request_text: str,
    reason: str,
) -> None:
    if not key:
        return
    _CONTEXTS[key] = {
        "kind": "pending_request",
        "tool": tool_name,
        "args": dict(args),
        "request_text": request_text,
        "reason": reason,
        "updated_at": datetime.now(timezone.utc),
    }


def pop_pending_request(key: str | None) -> dict[str, Any]:
    context = get_thread_context(key)
    if context.get("kind") != "pending_request":
        return {}
    _CONTEXTS.pop(str(key), None)
    return context


def format_context_note(ctx: dict[str, Any]) -> str:
    """Render the prior academy turn as a one-line ephemeral note for the body
    agent. Pure function over ctx fields only — no school/student/event names
    are baked in (this ships as a product to many academies). Returns '' when
    there is no inheritable prior context to hand off.
    """
    kind = ctx.get("kind")
    if not kind or kind == "pending_request":
        return ""
    tool = str(ctx.get("tool") or "").strip()
    parts: list[str] = []
    has_inline_data = False
    if kind == "monthly_test":
        month = str(ctx.get("test_month") or "").strip()
        subject = f"{month} 월말 테스트" if month else "직전 월말 테스트"
        parts.append(f"방금 사용자는 '{subject}'의 기록 데이터를 받았어.")
        data_block = _monthly_test_data_block(ctx)
        if data_block:
            parts.append(data_block)
            has_inline_data = True
    elif kind == "student":
        name = str(ctx.get("student_query") or "").strip()
        parts.append(f"방금 대화의 주제는 학생 '{name}'이었어." if name else "방금 대화는 특정 학생에 대한 거였어.")
    elif kind == "staff":
        name = str(ctx.get("staff_query") or "").strip()
        parts.append(f"방금 대화의 주제는 강사/직원 '{name}'이었어." if name else "방금 대화는 특정 강사/직원에 대한 거였어.")
    elif kind == "assignment":
        date_text = str(ctx.get("date") or "").strip()
        parts.append(f"방금 대화는 {date_text} 반배치 조회였어." if date_text else "방금 대화는 반배치 조회였어.")
    else:  # generic — carry whatever inheritable entity was in play
        entity = next(
            (str(ctx.get(name)).strip() for name in INHERITABLE_ENTITY_ARGS if not _is_blank(ctx.get(name))),
            "",
        )
        if not entity:
            return ""
        parts.append(f"방금 대화의 주제는 '{entity}'이었어.")
    if tool:
        parts.append(f"(직전에 사용한 학원 도구: {tool})")
    if has_inline_data:
        parts.append(
            "이번 질문이 위 데이터에 이어지는 후속이면(특정 학생만·특정 종목만·평균·비교 등), "
            "위 데이터에서 바로 골라내서 답해 — 같은 걸 다시 조회하지 말고 정확하고 빠르게."
        )
    else:
        parts.append(
            "사용자의 이번 질문이 그 직전 내용에 이어지는 후속이면, 새 주제로 넘기지 말고 그 직전 데이터를 기준으로 해석해. "
            "예를 들어 '그 사람만'·'그것만 빼줘'·'특정 항목만'은 직전 데이터에서 골라내라는 뜻이지 전혀 다른 조회가 아니야. "
            "필요하면 직전과 같은 학원 도구/데이터를 다시 불러서 거기서 처리해."
        )
    parts.append(
        "답을 내기 전에 스스로 한 번 검수해: 이 답이 사용자가 방금 한 질문에 실제로 맞는 답인가? "
        "결과가 비었거나 '못 찾았다' 류로 끝나면, 추측해서 넘기지 말고 직전 맥락을 활용해 다른 도구/접근으로 다시 시도해. "
        "그래도 안 되면 틀린 답을 내지 말고 무엇이 왜 막혔는지 솔직히 말해."
    )
    return " ".join(parts)


_MAX_INLINE_PARTICIPANTS = 80


def _monthly_test_data_block(ctx: dict[str, Any]) -> str:
    """Render the remembered roster compactly so the body agent can filter it
    directly next turn — no re-fetch, so accuracy AND speed. Capped so the
    ephemeral note never blows up the prompt for an unusually large test."""
    participants = ctx.get("participants")
    if not isinstance(participants, list) or not participants:
        return ""
    record_types = ctx.get("record_types") if isinstance(ctx.get("record_types"), list) else []
    rt_brief = [
        {"id": str(r.get("record_type_id") or r.get("id") or ""), "name": r.get("name"), "unit": r.get("unit")}
        for r in record_types
        if isinstance(r, dict)
    ]
    rows = [p for p in participants if isinstance(p, dict)]
    p_brief = [
        {"name": p.get("name"), "gender": p.get("gender"), "school": p.get("school"), "records": p.get("records")}
        for p in rows[:_MAX_INLINE_PARTICIPANTS]
    ]
    note = (
        "아래는 그때 받아온 전체 참가자 원본 데이터야:\n"
        f"종목정의={json.dumps(rt_brief, ensure_ascii=False)}\n"
        f"참가자={json.dumps(p_brief, ensure_ascii=False)}"
    )
    if len(rows) > _MAX_INLINE_PARTICIPANTS:
        note += (
            f"\n(참가자가 많아 처음 {_MAX_INLINE_PARTICIPANTS}명만 실었어. "
            "이 안에 못 찾으면 academy_monthly_test_records로 다시 조회해.)"
        )
    return note


def clear_thread_contexts() -> None:
    _CONTEXTS.clear()
