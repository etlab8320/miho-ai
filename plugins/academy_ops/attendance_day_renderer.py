"""HTML-first PNG renderer for daily academy attendance rosters."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from miho_constants import get_miho_dir

from .attendance_day_template import attendance_day_image_height, render_attendance_day_html
from .brand_assets import academy_brand_logo_path
from .student_card_capture import StudentCardCaptureError, capture_html_to_png


class AttendanceDayRosterRenderError(RuntimeError):
    pass


class AttendanceDayRosterImageRenderer:
    def __init__(self, output_dir: Path | None = None, work_dir: Path | None = None) -> None:
        root = get_miho_dir("cache/media", "media_cache")
        self._output_dir = output_dir or root / "academy_attendance_days"
        self._work_dir = work_dir or root / "academy_attendance_days_html"

    def render(self, payload: dict) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        base = self._filename_base(payload)
        html_path = self._work_dir / f"{base}.html"
        image_path = self._output_dir / f"{base}.png"
        html_path.write_text(
            render_attendance_day_html(payload, logo_path=academy_brand_logo_path()),
            encoding="utf-8",
        )
        try:
            capture_html_to_png(html_path, image_path, width=1200, height=attendance_day_image_height(payload))
        except StudentCardCaptureError as exc:
            raise AttendanceDayRosterRenderError(str(exc)) from exc
        return image_path

    def _filename_base(self, payload: dict) -> str:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        rows = sum(len(rows) for rows in (payload.get("slots") or {}).values())
        seed = f"{payload.get('date')}:{rows}:{stamp}"
        digest = hashlib.sha256(seed.encode()).hexdigest()[:10]
        return f"attendance-day-{digest}"
