"""Student performance record chart image tool."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from html import escape
import json
import struct
import uuid
from typing import Any

from miho_constants import get_miho_home

from .academy_api import AcademyApiError
from .academy_query_tools import _date_arg, _int_arg, _json_error, _json_ok, _resolve_client
from .response_guidance import academy_response_guidance
from .student_card_capture import StudentCardCaptureError, capture_html_to_png
from .student_lookup import StudentLookupAmbiguous, StudentLookupNotFound, resolve_paca_student
from .student_records_tool import _event_matches, _float_or_none, _record_day

CHART_CANVAS_WIDTH = 1240
PNG_HEADER_BYTES = 24
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
IMAGE_QA_ERROR_MESSAGE = "실기 그래프 이미지 검수에 실패했어. 관리자에게 문의해줘."


def register_student_record_chart_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_student_record_chart_image",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_query": {"type": "string", "description": "학생 이름, 학교, 또는 PACA 검색어."},
                "event_query": {"type": "string", "description": "특정 종목만 그릴 때의 종목명. 전체면 빈 문자열."},
                "today": {"type": "string", "description": "기준 날짜. YYYY-MM-DD 형식."},
                "period_days": {"type": "integer", "minimum": 1, "maximum": 365, "default": 180},
                "limit": {"type": "integer", "minimum": 2, "maximum": 10, "default": 5},
            },
            "required": ["student_query"],
            "additionalProperties": False,
        },
        handler=_student_record_chart_image_tool_handler,
        description=(
            "Create a PNG chart for one student's Peak practical-test records. "
            "Use for requests like recent N attempts, per-event trend graph, 실기 기록 그래프, 측정 기록 이미지. "
            "It resolves the PACA student, maps to Peak, reads records, groups by event, and returns MEDIA:<path>."
        ),
    )


def _student_record_chart_image_tool_handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
    payload = args or {}
    query = str(payload.get("student_query") or "").strip()
    if not query:
        return _json_error("학생 이름이나 검색어를 알려줘.")
    event_query = str(payload.get("event_query") or "").strip()
    today = _date_arg(payload.get("today")) or date.today()
    period_days = _int_arg(payload.get("period_days"), default=180, maximum=365)
    limit = _int_arg(payload.get("limit"), default=5, maximum=10)
    client_or_error = _resolve_client(kwargs.get("client"))
    if isinstance(client_or_error, str):
        return _json_error(client_or_error)
    try:
        student = resolve_paca_student(client_or_error, query)
        peak_student = _peak_student_for_paca(client_or_error.list_peak_students(), int(student.get("id") or 0))
        if peak_student is None:
            return _json_error(f"{_student_name(student)} Peak 학생 매핑을 찾지 못했어.")
        rows = client_or_error.list_peak_records(int(peak_student.get("id") or 0))
    except StudentLookupNotFound:
        return _json_error("학생을 찾지 못했어. 이름이나 학교를 조금 더 정확히 알려줘.")
    except StudentLookupAmbiguous as exc:
        return _json_error(f"동명이인이 있어. 학생을 조금 더 구체적으로 골라줘: {exc}")
    except (AcademyApiError, ValueError) as exc:
        return _json_error(str(exc))

    groups = _record_groups(rows, today=today, period_days=period_days, event_query=event_query, limit=limit)
    student_name = _student_name(student)
    if not groups:
        label = event_query or "실기"
        return _json_error(f"{student_name} 최근 {period_days}일간 {label} 기록은 없어.")
    try:
        image_path = _render_chart_image(student_name, groups, limit=limit, today=today, period_days=period_days)
    except StudentCardCaptureError as exc:
        return _json_error(str(exc))
    media_tag = f"MEDIA:{image_path}"
    return _json_ok(
        {
            "operation": "student.record_chart_image",
            "student": {
                "paca_student_id": int(student.get("id") or 0),
                "peak_student_id": int(peak_student.get("id") or 0),
                "name": student_name,
            },
            "event_query": event_query,
            "period_days": period_days,
            "limit": limit,
            "events": [_public_group(group) for group in groups],
            "message": f"{student_name} 최근 {limit}회차 실기 그래프야. {media_tag}",
            "image_path": str(image_path),
            "media_tag": media_tag,
            "assistant_guidance": academy_response_guidance(use_message_as_facts=True),
        }
    )


def _record_groups(
    rows: list[dict[str, Any]],
    *,
    today: date,
    period_days: int,
    event_query: str,
    limit: int,
) -> list[dict[str, Any]]:
    first_day = today - timedelta(days=max(1, period_days) - 1)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if not isinstance(row, dict):
            continue
        measured_day = _record_day(row.get("measured_at"))
        value = _float_or_none(row.get("value"))
        event_name = str(row.get("record_type_name") or "기록")
        if measured_day is None or value is None:
            continue
        if not (first_day <= measured_day <= today):
            continue
        if event_query and not _event_matches(event_query, event_name):
            continue
        buckets[event_name].append(
            {
                "event_name": event_name,
                "measured_at": str(row.get("measured_at") or measured_day.isoformat()),
                "day": measured_day,
                "value": value,
                "unit": str(row.get("unit") or ""),
                "direction": str(row.get("direction") or ""),
            }
        )
    groups = []
    for event_name, items in buckets.items():
        latest = sorted(items, key=lambda item: item["measured_at"], reverse=True)[:limit]
        latest.sort(key=lambda item: item["measured_at"])
        groups.append({"event_name": event_name, "records": latest, "latest": latest[-1]["measured_at"]})
    groups.sort(key=lambda item: str(item["latest"]), reverse=True)
    return groups


def _render_chart_image(
    student_name: str,
    groups: list[dict[str, Any]],
    *,
    limit: int,
    today: date,
    period_days: int,
) -> str:
    out_dir = get_miho_home() / "media_cache" / "academy_record_charts"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex[:12]
    html_path = out_dir / f"{stem}.html"
    image_path = out_dir / f"{stem}.png"
    html_path.write_text(_chart_html(student_name, groups, limit=limit, today=today, period_days=period_days), encoding="utf-8")
    height = _chart_height(groups)
    capture_html_to_png(html_path, image_path, width=CHART_CANVAS_WIDTH, height=height)
    _validate_chart_image(image_path, width=CHART_CANVAS_WIDTH, min_height=height)
    return str(image_path)


def _chart_html(student_name: str, groups: list[dict[str, Any]], *, limit: int, today: date, period_days: int) -> str:
    cards = "\n".join(_event_card(group) for group in groups)
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><style>{_css()}</style></head>
<body><main class="sheet">
  <header><div class="eyebrow">Peak practical records</div>
    <h1>{escape(student_name)} 최근 {limit}회차 실기 그래프</h1>
    <p>기준일 {today.isoformat()} · 최근 {period_days}일 · 종목별 최신 기록 흐름</p>
  </header>
  <section class="grid">{cards}</section>
  <footer>민감정보 제외 · PACA/Peak 조회 데이터 기준</footer>
</main></body></html>"""


def _event_card(group: dict[str, Any]) -> str:
    records = group["records"]
    latest = records[-1]
    scores = [_score(item) for item in records]
    delta = scores[-1] - scores[0] if len(scores) > 1 else 0.0
    sign = "+" if delta > 0 else ""
    rows = "".join(
        f"<tr><td>{escape(str(item['measured_at'])[:10])}</td><td>{item['value']:g}{escape(item['unit'])}</td></tr>"
        for item in reversed(records)
    )
    return f"""<article class="card">
  <div class="card-head"><h2>{escape(group['event_name'])}</h2>
    <strong>{latest['value']:g}{escape(latest['unit'])}</strong></div>
  <div class="delta">{sign}{delta:g}{escape(latest['unit'])} / {len(records)}회</div>
  {_svg(records)}
  <table><tbody>{rows}</tbody></table>
</article>"""


def _svg(records: list[dict[str, Any]]) -> str:
    width, height = 500, 160
    values = [_score(item) for item in records]
    low, high = min(values), max(values)
    span = high - low or 1.0
    points = []
    for index, value in enumerate(values):
        x = 28 if len(values) == 1 else 28 + index * ((width - 56) / (len(values) - 1))
        y = 24 + (high - value) / span * (height - 52)
        points.append((x, y))
    circles = "".join(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='5'/>" for x, y in points)
    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f"<svg viewBox='0 0 {width} {height}'><polyline points='{polyline}'/>{circles}</svg>"


def _score(record: dict[str, Any]) -> float:
    value = float(record["value"])
    return -value if _is_lower_better(record) else value


def _is_lower_better(record: dict[str, Any]) -> bool:
    direction = str(record.get("direction") or "").strip().lower()
    if direction:
        return direction in {"lower", "low", "asc", "less", "fast", "낮을수록"}
    return str(record.get("unit") or "").strip().lower() in {"초", "s", "sec", "second", "seconds"}


def _css() -> str:
    return """
body{margin:0;background:#eef0f4;color:#16181d;font-family:-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo",sans-serif}
.sheet{width:1160px;margin:0 auto;padding:42px}.eyebrow{font-size:18px;font-weight:800;color:#3e5d8f;text-transform:uppercase}
h1{margin:8px 0 6px;font-size:44px;letter-spacing:0}p{margin:0;color:#5d6470;font-size:20px}.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:30px}
.card{background:#fff;border:1px solid #dfe3ea;border-radius:8px;padding:22px;box-shadow:0 14px 34px rgba(30,38,55,.08)}
.card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.card h2{margin:0;font-size:25px}.card strong{font-size:26px;font-variant-numeric:tabular-nums}
.delta{margin:8px 0 10px;color:#3e6f51;font-size:18px;font-weight:800}svg{width:100%;height:172px;background:#f7f9fc;border-radius:8px}
polyline{fill:none;stroke:#2f6fed;stroke-width:5;stroke-linecap:round;stroke-linejoin:round}circle{fill:#fff;stroke:#2f6fed;stroke-width:4}
table{width:100%;border-collapse:collapse;margin-top:12px;font-size:17px}td{padding:7px 0;border-bottom:1px solid #edf0f4}td:last-child{text-align:right;font-weight:800;font-variant-numeric:tabular-nums}
footer{margin-top:24px;color:#78808c;font-size:16px}
"""


def _chart_height(groups: list[dict[str, Any]]) -> int:
    total = 250
    for index in range(0, len(groups), 2):
        row = groups[index : index + 2]
        max_records = max((len(group.get("records") or []) for group in row), default=0)
        total += 330 + max_records * 36
        if index:
            total += 18
    return min(8000, max(760, total + 100))


def _validate_chart_image(image_path: Any, *, width: int, min_height: int) -> None:
    dimensions = _png_dimensions(image_path)
    if dimensions is None:
        raise StudentCardCaptureError(IMAGE_QA_ERROR_MESSAGE)
    actual_width, actual_height = dimensions
    if actual_width != width or actual_height < min_height:
        raise StudentCardCaptureError(IMAGE_QA_ERROR_MESSAGE)


def _png_dimensions(image_path: Any) -> tuple[int, int] | None:
    try:
        header = image_path.read_bytes()[:PNG_HEADER_BYTES]
    except OSError:
        return None
    if len(header) < PNG_HEADER_BYTES or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", header[16:24])
    if width <= 0 or height <= 0:
        return None
    return width, height


def _public_group(group: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_name": group["event_name"],
        "records": [
            {"measured_at": item["measured_at"], "value": item["value"], "unit": item["unit"]}
            for item in group["records"]
        ],
    }


def _peak_student_for_paca(students: list[dict[str, Any]], paca_student_id: int) -> dict[str, Any] | None:
    for student in students:
        if int(student.get("paca_student_id") or 0) == paca_student_id:
            return student
    return None


def _student_name(student: dict[str, Any]) -> str:
    return str(student.get("name") or "학생")
