"""Shared academy brand assets for HTML image renderers."""

from __future__ import annotations

import base64
import os
from pathlib import Path


BRAND_LOGO_ENV = "MIHO_ACADEMY_BRAND_LOGO_PATH"
BUNDLED_STAMP_PATH = Path(__file__).resolve().parent / "assets" / "stamp.png"
LEGACY_BUNDLED_STAMP_PATH = Path(__file__).resolve().parent / "assets" / "max_stamp.png"
_IMAGE_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


def academy_brand_logo_path() -> Path | None:
    env_path = os.environ.get(BRAND_LOGO_ENV, "").strip()
    for candidate in _candidate_paths(env_path):
        if candidate.exists():
            return candidate
    return None


def academy_brand_logo_src(path: Path | None = None) -> str | None:
    logo_path = path or academy_brand_logo_path()
    if logo_path is None or not logo_path.exists():
        return None
    mime_type = _IMAGE_MIME_TYPES.get(logo_path.suffix.lower(), "application/octet-stream")
    try:
        encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return f"data:{mime_type};base64,{encoded}"


def _candidate_paths(env_path: str) -> tuple[Path, ...]:
    paths: list[Path] = []
    if env_path:
        paths.append(Path(env_path).expanduser())
    paths.extend(
        [
            BUNDLED_STAMP_PATH,
            LEGACY_BUNDLED_STAMP_PATH,
        ]
    )
    return tuple(paths)
