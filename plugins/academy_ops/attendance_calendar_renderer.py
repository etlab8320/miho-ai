"""HTML-first PNG renderer for student attendance calendars."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
import os

from miho_constants import get_miho_dir

from .attendance_calendar_template import calendar_image_height, render_attendance_calendar_html
from .student_card_capture import StudentCardCaptureError, capture_html_to_png


class AttendanceCalendarRenderError(RuntimeError):
    pass


class AttendanceCalendarImageRenderer:
    def __init__(self, output_dir: Path | None = None, work_dir: Path | None = None) -> None:
        root = get_miho_dir("cache/media", "media_cache")
        self._output_dir = output_dir or root / "academy_attendance_calendars"
        self._work_dir = work_dir or root / "academy_attendance_calendars_html"

    def render(self, payload: dict) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        base = self._filename_base(payload)
        html_path = self._work_dir / f"{base}.html"
        image_path = self._output_dir / f"{base}.png"
        html_path.write_text(render_attendance_calendar_html(payload, logo_path=_logo_path()), encoding="utf-8")
        try:
            capture_html_to_png(html_path, image_path, width=1200, height=calendar_image_height(payload))
        except StudentCardCaptureError as exc:
            raise AttendanceCalendarRenderError(str(exc)) from exc
        return image_path

    def _filename_base(self, payload: dict) -> str:
        student = payload.get("student") if isinstance(payload.get("student"), dict) else {}
        paca_id = str(student.get("paca_student_id") or "student")
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        seed = f"{paca_id}:{payload.get('start_date')}:{payload.get('end_date')}:{stamp}"
        digest = hashlib.sha256(seed.encode()).hexdigest()[:10]
        return f"attendance-calendar-{paca_id}-{digest}"


def _logo_path() -> Path | None:
    env_path = os.environ.get("MIHO_ACADEMY_BRAND_LOGO_PATH", "").strip()
    for candidate in (env_path, "/Users/etlab/etlab/logo/stamp.png", _bundled_logo()):
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return path
    return None


def _bundled_logo() -> str:
    return str(Path(__file__).resolve().parent / "assets" / "max_stamp.png")
