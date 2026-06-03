"""Fast follow-up responses for previously fetched Peak assignments."""

from __future__ import annotations

from typing import Any


def assignment_count_followup_response(text: str, context: dict[str, Any]) -> str:
    if context.get("kind") != "assignment" or not _looks_like_count_followup(text):
        return ""
    slots = context.get("slots")
    if not isinstance(slots, dict) or not slots:
        return ""
    date_text = str(context.get("date") or "").strip()
    heading = f"{date_text} 반배치 각 반 인원".strip()
    lines = [heading]
    for slot, body in slots.items():
        if not isinstance(body, dict):
            continue
        classes = _dict_rows(body.get("classes"))
        waiting = _dict_rows(body.get("waiting_students"))
        if not classes and not waiting:
            continue
        lines.append(_slot_label(str(slot)))
        for class_row in classes:
            lines.append(_class_line(class_row))
        waiting_names = _names(waiting, key="student_name")
        if waiting_names:
            lines.append(f"- 미배정 ({len(waiting_names)}명): {', '.join(waiting_names)}")
    return "\n".join(lines)


def _looks_like_count_followup(text: str) -> bool:
    normalized = "".join(str(text or "").split())
    if not normalized:
        return False
    if any(word in normalized for word in ("출근", "강사", "상담", "결제")):
        return False
    count_markers = ("몇명", "명씩", "인원", "인원표시", "맨뒤", "뒤에")
    assignment_markers = ("반배치", "각반", "수업배정")
    if any(marker in normalized for marker in assignment_markers):
        return any(marker in normalized for marker in count_markers)
    return any(marker in normalized for marker in count_markers)


def _class_line(class_row: dict[str, Any]) -> str:
    class_num = class_row.get("class_num")
    class_name = f"{class_num}반" if class_num else "반 미지정"
    instructors = _names(class_row.get("instructors"))
    teacher = f" / {', '.join(instructors)}" if instructors else ""
    student_names = _names(class_row.get("students"), key="student_name")
    roster = f": {', '.join(student_names)}" if student_names else ""
    return f"- {class_name}{teacher} ({len(student_names)}명){roster}"


def _names(rows: Any, *, key: str = "name") -> list[str]:
    return [str(row.get(key) or "").strip() for row in _dict_rows(rows) if str(row.get(key) or "").strip()]


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [row for row in value or [] if isinstance(row, dict)] if isinstance(value, list) else []


def _slot_label(value: str) -> str:
    return {"morning": "오전반", "afternoon": "오후반", "evening": "저녁반"}.get(value, value or "시간대 미지정")
