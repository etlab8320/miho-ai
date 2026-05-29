"""HTML-first PNG renderer for academy consultation candidates."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
import os

from miho_constants import get_miho_dir

from .consultation_candidate_template import (
    consultation_candidates_image_height,
    render_consultation_candidates_html,
)
from .student_card_capture import StudentCardCaptureError, capture_html_to_png


class ConsultationCandidateRenderError(RuntimeError):
    pass


class ConsultationCandidateImageRenderer:
    def __init__(self, output_dir: Path | None = None, work_dir: Path | None = None) -> None:
        root = get_miho_dir("cache/media", "media_cache")
        self._output_dir = output_dir or root / "academy_consultation_candidates"
        self._work_dir = work_dir or root / "academy_consultation_candidates_html"

    def render(self, payload: dict) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._work_dir.mkdir(parents=True, exist_ok=True)
        base = self._filename_base(payload)
        html_path = self._work_dir / f"{base}.html"
        image_path = self._output_dir / f"{base}.png"
        html_path.write_text(render_consultation_candidates_html(payload, logo_path=_logo_path()), encoding="utf-8")
        try:
            capture_html_to_png(
                html_path,
                image_path,
                width=1200,
                height=consultation_candidates_image_height(payload),
            )
        except StudentCardCaptureError as exc:
            raise ConsultationCandidateRenderError(str(exc)) from exc
        return image_path

    def _filename_base(self, payload: dict) -> str:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        seed = f"{payload.get('today')}:{payload.get('period_days')}:{len(payload.get('candidates') or [])}:{stamp}"
        digest = hashlib.sha256(seed.encode()).hexdigest()[:10]
        return f"consultation-candidates-{digest}"


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
