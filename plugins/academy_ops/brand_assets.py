"""Shared academy brand assets for HTML image renderers."""

from __future__ import annotations

import os
from pathlib import Path


BRAND_LOGO_ENV = "MIHO_ACADEMY_BRAND_LOGO_PATH"
BUNDLED_STAMP_PATH = Path(__file__).resolve().parent / "assets" / "stamp.png"
LEGACY_BUNDLED_STAMP_PATH = Path(__file__).resolve().parent / "assets" / "max_stamp.png"


def academy_brand_logo_path() -> Path | None:
    env_path = os.environ.get(BRAND_LOGO_ENV, "").strip()
    for candidate in _candidate_paths(env_path):
        if candidate.exists():
            return candidate
    return None


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
