"""Offline-embedded webfonts for academy report rendering.

The headless Chromium that renders reports may run on a sold linux VPS with no
internet and no Korean system fonts. To guarantee the report always renders in a
high-quality Korean typeface (never a blocky system fallback), the Pretendard
woff2 files are bundled under ``assets/`` and inlined as base64 ``@font-face``
``src`` so nothing is fetched at render time. CDN ``@import`` is intentionally
avoided as the primary source.
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"

# (file stem, font-weight) — Pretendard static weights bundled in assets/.
_PRETENDARD_FACES: tuple[tuple[str, int], ...] = (
    ("Pretendard-Regular", 400),
    ("Pretendard-Medium", 500),
    ("Pretendard-SemiBold", 600),
    ("Pretendard-Bold", 700),
)

PRETENDARD_FAMILY = "PretendardLocal"


@lru_cache(maxsize=1)
def report_font_css() -> str:
    """Inline @font-face rules for the bundled Korean report font.

    Returns an empty string if no font file is present, so the CSS fallback
    chain still applies.
    """
    rules: list[str] = []
    for stem, weight in _PRETENDARD_FACES:
        encoded = _encode_woff2(_ASSETS_DIR / f"{stem}.woff2")
        if encoded is None:
            continue
        rules.append(
            f"@font-face{{font-family:'{PRETENDARD_FAMILY}';"
            f"src:url('data:font/woff2;base64,{encoded}') format('woff2');"
            f"font-weight:{weight};font-style:normal;font-display:block;}}"
        )
    return "".join(rules)


def _encode_woff2(path: Path) -> str | None:
    try:
        return base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
