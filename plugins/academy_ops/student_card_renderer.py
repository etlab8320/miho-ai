"""HTML-first PNG renderer for academy student cards."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from miho_constants import get_miho_dir

from .brand_assets import academy_brand_logo_path
from .student_card import StudentCard
from .student_card_capture import StudentCardCaptureError, capture_html_to_png
from .student_card_template import render_student_card_html


class StudentCardRenderError(RuntimeError):
    pass


class StudentCardImageRenderer:
    def __init__(self, output_dir: Path | None = None, work_dir: Path | None = None) -> None:
        root = get_miho_dir("cache/media", "media_cache")
        self._output_dir = output_dir or root / "academy_cards"
        self._work_dir = work_dir or root / "academy_cards_html"

    def render(self, card: StudentCard) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        base = self._filename_base(card)
        html_path = self._work_dir / f"{base}.html"
        image_path = self._output_dir / f"{base}.png"
        html_path.write_text(render_student_card_html(card, logo_path=academy_brand_logo_path()), encoding="utf-8")
        try:
            capture_html_to_png(html_path, image_path, width=1200, height=1340)
        except StudentCardCaptureError as exc:
            raise StudentCardRenderError(str(exc)) from exc
        return image_path

    def _filename_base(self, card: StudentCard) -> str:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        digest = hashlib.sha256(f"{card.profile.paca_student_id}:{stamp}".encode()).hexdigest()[:10]
        return f"student-card-{card.profile.paca_student_id}-{digest}"
