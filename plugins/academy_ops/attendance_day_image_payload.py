"""Image payload enrichment for daily academy attendance rosters."""

from __future__ import annotations

from typing import Any

from .attendance_day_renderer import AttendanceDayRosterImageRenderer, AttendanceDayRosterRenderError


def with_attendance_day_image(payload: dict[str, Any], renderer: Any = None) -> dict[str, Any]:
    active_renderer = renderer or AttendanceDayRosterImageRenderer()
    try:
        image_path = active_renderer.render(payload)
    except AttendanceDayRosterRenderError as exc:
        enriched = dict(payload)
        enriched["image_error"] = str(exc)
        enriched["message"] = (
            "출석 명단은 조회했지만 이미지 파일 생성에 실패했어. "
            "아래 요약으로 먼저 확인해줘.\n"
            f"{payload.get('message', '')}"
        ).strip()
        return enriched
    media_tag = f"MEDIA:{image_path}"
    enriched = dict(payload)
    enriched["image_path"] = str(image_path)
    enriched["media_tag"] = media_tag
    enriched["message"] = f"{payload.get('message', '')}\n출석 명단 이미지야. {media_tag}".strip()
    return enriched
