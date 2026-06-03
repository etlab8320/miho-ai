"""Fast follow-up responses for previously fetched Peak assignments."""

from __future__ import annotations

import html
import json
from typing import Any

from .render_image_tool import _render_image_tool_handler


def assignment_count_followup_response(text: str, context: dict[str, Any]) -> str:
    if context.get("kind") != "assignment":
        return ""
    if _looks_like_image_followup(text):
        return _assignment_image_response(context)
    if not _looks_like_count_followup(text):
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


def _looks_like_image_followup(text: str) -> bool:
    normalized = "".join(str(text or "").split()).lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in ("이미지", "사진", "png", "캡처", "캡쳐"))


def _assignment_image_response(context: dict[str, Any]) -> str:
    slots = context.get("slots")
    if not isinstance(slots, dict) or not slots:
        return ""
    date_text = str(context.get("date") or "").strip()
    title = f"{date_text} 반배치".strip()
    raw = _render_image_tool_handler(
        {
            "html": _assignment_html(context),
            "title": title,
            "width": 1200,
            "height": _assignment_image_height(slots),
        }
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return str(raw or "").strip()
    if data.get("ok"):
        media = str(data.get("media_tag") or "").strip()
        return f"방금 반배치 기준으로 이미지로 정리했어. {media}".strip()
    return str(data.get("message") or "이미지 생성 중 오류가 났어.").strip()


def _assignment_html(context: dict[str, Any]) -> str:
    date_text = _esc(str(context.get("date") or ""))
    summary = context.get("summary") if isinstance(context.get("summary"), dict) else {}
    slots = context.get("slots") if isinstance(context.get("slots"), dict) else {}
    rows = "\n".join(_assignment_table_rows(slots))
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{date_text} 반배치</title>
<style>
body {{ margin: 0; background: #f6f7f9; color: #15171a; font-family: sans-serif; }}
.page {{ padding: 44px; }}
.title {{ font-size: 34px; font-weight: 800; margin-bottom: 10px; }}
.summary {{ color: #5f6875; font-size: 18px; margin-bottom: 24px; }}
table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 14px; overflow: hidden; }}
th, td {{ padding: 16px 18px; border-bottom: 1px solid #e7e9ee; vertical-align: top; font-size: 18px; }}
th {{ background: #20242a; color: white; font-size: 16px; text-align: left; }}
td.count, th.count {{ text-align: right; width: 90px; }}
td.students {{ line-height: 1.55; word-break: keep-all; }}
.slot {{ font-weight: 800; }}
.muted {{ color: #697383; }}
</style>
</head>
<body>
<main class="page">
<section class="title">{date_text} 반배치</section>
<section class="summary">{_summary_text(summary)}</section>
<table>
<thead><tr><th>시간</th><th>반 / 강사</th><th class="count">인원</th><th>명단</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</main>
</body>
</html>"""


def _assignment_table_rows(slots: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for slot, body in slots.items():
        if not isinstance(body, dict):
            continue
        slot_label = _esc(_slot_label(str(slot)))
        for class_row in _dict_rows(body.get("classes")):
            class_num = class_row.get("class_num")
            class_name = f"{class_num}반" if class_num else "반 미지정"
            instructors = ", ".join(_names(class_row.get("instructors"))) or "강사 미지정"
            student_names = _names(class_row.get("students"), key="student_name")
            rows.append(_table_row(slot_label, f"{class_name} / {instructors}", student_names))
        waiting_names = _names(body.get("waiting_students"), key="student_name")
        if waiting_names:
            rows.append(_table_row(slot_label, "미배정", waiting_names, muted=True))
    return rows or ['<tr><td colspan="4" class="muted">반배치 데이터가 없어.</td></tr>']


def _table_row(slot: str, label: str, student_names: list[str], *, muted: bool = False) -> str:
    label_class = ' class="muted"' if muted else ""
    roster = ", ".join(_esc(name) for name in student_names) or "-"
    return (
        "<tr>"
        f'<td class="slot">{slot}</td>'
        f"<td{label_class}>{_esc(label)}</td>"
        f'<td class="count">{len(student_names)}명</td>'
        f'<td class="students">{roster}</td>'
        "</tr>"
    )


def _assignment_image_height(slots: dict[str, Any]) -> int:
    rows = 0
    students = 0
    for body in slots.values():
        if not isinstance(body, dict):
            continue
        classes = _dict_rows(body.get("classes"))
        waiting = _dict_rows(body.get("waiting_students"))
        rows += len(classes) + (1 if waiting else 0)
        for class_row in classes:
            students += len(_names(class_row.get("students"), key="student_name"))
        students += len(_names(waiting, key="student_name"))
    return max(560, min(8000, 310 + rows * 82 + students * 10))


def _summary_text(summary: dict[str, Any]) -> str:
    return (
        f"{summary.get('classes', 0)}개 반 · "
        f"배정 {summary.get('assigned_students', 0)}명 · "
        f"미배정 {summary.get('waiting_students', 0)}명"
    )


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


def _esc(value: str) -> str:
    return html.escape(value, quote=True)
