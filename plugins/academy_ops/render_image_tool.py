"""General-purpose HTML-to-image tool for academy data.

Most academy image needs already have a dedicated tool (attendance roster,
attendance calendar, student card, tabular report). When a request has no
dedicated tool, the model should NOT hunt through source code — it should fetch
the data with an existing read tool, build an HTML document itself, and hand
that HTML to this tool. The HTML is rendered to a PNG via the same Chromium
capture every other academy image tool uses, and returned with the standard
MEDIA:<path> contract for Discord delivery.

Unlike academy_report_image (fixed table layout), this places nothing for the
model — the model owns the full HTML, so it can render any layout (명단, 카드,
일정표, 비교표 등). Use academy_report_image when the data is a plain ranked
table; use this when the layout is freeform.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from miho_constants import get_miho_home

from .render_base_style import inject_base_style
from .student_card_capture import StudentCardCaptureError, capture_html_to_png


def _json_error(message: str) -> str:
    return json.dumps({"ok": False, "message": message}, ensure_ascii=False)


def _clamp(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(int(value), maximum))
    except (TypeError, ValueError):
        return default


def _render_image_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    payload = args or {}
    html = str(payload.get("html") or "").strip()
    if not html:
        return _json_error("이미지로 만들 HTML(html)이 필요해. 조회한 데이터로 HTML을 직접 구성해서 넘겨줘.")
    title = str(payload.get("title") or "이미지").strip()
    width = _clamp(payload.get("width"), default=1200, minimum=320, maximum=2400)
    height = _clamp(payload.get("height"), default=1400, minimum=320, maximum=8000)

    out_dir = get_miho_home() / "media_cache" / "academy_renders"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = uuid.uuid4().hex[:12]
    html_path = out_dir / f"{stem}.html"
    image_path = out_dir / f"{stem}.png"
    # Inject the common quality base (Korean webfont, tabular-nums, aligned
    # tables, clean spacing) so raw model HTML renders tidy and lined-up. The
    # base is a first-in-<head> layer the model's own styles override.
    html_path.write_text(inject_base_style(html), encoding="utf-8")

    try:
        capture_html_to_png(html_path, image_path, width=width, height=height)
    except StudentCardCaptureError as exc:
        return _json_error(str(exc))

    media_tag = f"MEDIA:{image_path}"
    return json.dumps(
        {
            "ok": True,
            "message": f"{title} 이미지야. {media_tag}",
            "image_path": str(image_path),
            "media_tag": media_tag,
        },
        ensure_ascii=False,
    )


def register_render_image_tool(ctx: Any) -> None:
    ctx.register_tool(
        name="academy_render_image",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "html": {
                    "type": "string",
                    "description": (
                        "렌더할 HTML. 네가(미호) 조회한 데이터로 직접 구성한다. 완성된 문서(<html>…</html>)든 "
                        "본문 조각(<table>…</table>, <ul>…</ul> 등)이든 다 받는다. "
                        "한국어 폰트·여백·기본 골격은 이 도구가 공통 스타일을 자동 주입한다(폰트/리셋/패딩/숫자 tabular). "
                        "하지만 표의 '정렬'은 네가 직접 지정해야 한다 — 기본 스타일은 정렬을 강제하지 않으니, "
                        "네가 안 넣으면 줄이 안 맞는다. 표 작성 규칙(반드시 지켜라):\n"
                        "① 표는 <table><thead><tr><th>…</th></tr></thead><tbody><tr><td>…</td></tr></tbody></table> 형태로. "
                        "헤더(th)와 값(td)의 열 순서를 동일하게 맞추고, 값을 빈 칸 없이 같은 열에 넣어라.\n"
                        "② 같은 컬럼은 헤더(th)와 셀(td)의 text-align을 반드시 동일하게 지정해라. "
                        "이름·학교·반 같은 텍스트 컬럼 = left, 점수·기록·cm·초·등급·인원수 같은 숫자 컬럼 = right.\n"
                        "③ 숫자/기록 셀은 우측정렬 + tabular로 자릿수가 맞게(이 도구가 tabular-nums는 깔아두니 정렬만 right로). \n"
                        "④ 컬럼 폭은 내용에 맞게. 헤더가 길면 줄바꿈을 허용해 잘리지 않게 해라(필요하면 그 th에 white-space:normal).\n"
                        "⑤ 정렬·폭은 inline style이나 네 자체 <style>로 직접 지정해라. 주입되는 기본 스타일은 폰트/리셋만 깔고 "
                        "정렬은 건드리지 않으므로 네 스타일이 그대로 적용된다.\n"
                        "예: <table>"
                        "<colgroup><col style='width:42px'><col><col style='width:140px'><col style='width:90px'></colgroup>"
                        "<thead><tr>"
                        "<th style='text-align:right'>No</th>"
                        "<th style='text-align:left'>이름</th>"
                        "<th style='text-align:left'>학교</th>"
                        "<th style='text-align:right'>기록</th>"
                        "</tr></thead><tbody><tr>"
                        "<td style='text-align:right'>1</td>"
                        "<td style='text-align:left'>홍길동</td>"
                        "<td style='text-align:left'>서울고</td>"
                        "<td style='text-align:right'>2.45</td>"
                        "</tr></tbody></table>\n"
                        "데이터는 이 도구가 가져오지 않으므로, 이미 조회 도구로 확보한 행만으로 표/카드/목록을 만들어 넣어라."
                    ),
                },
                "title": {"type": "string", "description": "이미지 설명용 짧은 제목. 응답 문구에만 쓰임."},
                "width": {
                    "type": "integer",
                    "minimum": 320,
                    "maximum": 2400,
                    "default": 1200,
                    "description": "렌더 폭(px). 기본 1200.",
                },
                "height": {
                    "type": "integer",
                    "minimum": 320,
                    "maximum": 8000,
                    "default": 1400,
                    "description": "렌더 높이(px). 내용이 잘리지 않게 행 수에 맞춰 넉넉히 잡아라. 기본 1400.",
                },
            },
            "required": ["html"],
            "additionalProperties": False,
        },
        handler=_render_image_tool_handler,
        description=(
            "학원(PACA/Peak) 데이터를 표·명단·이미지로 보여줘야 하는데 전용 이미지 도구가 정확히 맞지 않을 때 쓰는 "
            "범용 렌더러. 너(미호)가 직접 HTML을 구성해 이 도구로 PNG로 만들고 Discord에 첨부한다 "
            "(MEDIA:<path> 반환). "
            "처리 흐름: ① 전용 도구는 본래 용도에만 — attendance_day 이미지는 '이미 체크된 출결 현황', "
            "attendance_calendar 이미지는 '학생 출석 달력', student_card 이미지는 '학생 관리카드'일 때만 써라. "
            "② 그 밖의 일반적인 '명단/표/임의 데이터를 이미지로' 요청(출석 예정 명단 이미지, 수업별 학생 표, 기록·순위 표 등)은 "
            "전용 도구로 새지 말고 이 도구가 기본 경로다 — 소스코드를 뒤지지 말고, "
            "먼저 데이터 조회 도구(academy_class_roster_range, academy_attendance_day, "
            "academy_student_record_lookup, academy_schedule_range 등)로 필요한 데이터를 얻은 다음, "
            "그 데이터로 네가 직접 HTML 표를 만들어 이 도구에 넘겨 이미지화해라. "
            "데이터는 이 도구가 가져오지 않는다 — 반드시 조회 도구로 먼저 데이터를 확보한 뒤 그 사실만으로 HTML을 구성해라. "
            "표를 만들 땐 html 인자 설명의 표 작성 규칙(같은 컬럼은 헤더·셀 정렬 일치, 텍스트=left·숫자=right, 잘림 방지)을 "
            "반드시 지켜야 줄이 맞는다. 자유로운 레이아웃이 필요할 때 이 도구를, 고정된 단순 순위표면 academy_report_image를 써라."
        ),
    )
