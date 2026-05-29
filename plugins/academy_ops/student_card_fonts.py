"""Goyang typeface resolver for academy card rendering."""

from __future__ import annotations

from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import ZipFile
import base64
import io
import os

from miho_constants import get_miho_dir


GOYANG_DEOGYANG_URL = (
    "https://www.goyang.go.kr/component/resrce/file/"
    "ND_resrceFileDownload.do?resrceSn=167&resrceVer=1&fileSn=1"
)
GOYANG_LICENSE_NOTE = "고양덕양체: 고양특례시 제공, 공공누리 제1유형"


def resolve_goyang_font() -> Path | None:
    cached = _cached_font_path()
    if cached.exists():
        return cached
    system = _find_system_goyang_font()
    if system is not None:
        return system
    downloaded = _download_to_cache(cached)
    if downloaded is not None:
        return downloaded
    return None


def goyang_font_css() -> str:
    font_path = resolve_goyang_font()
    if font_path is None:
        return ""
    try:
        encoded = base64.b64encode(font_path.read_bytes()).decode("ascii")
    except OSError:
        return ""
    return (
        "@font-face{font-family:'GoyangDeogyang';"
        f"src:url('data:font/ttf;base64,{encoded}') format('truetype');"
        "font-weight:700;font-style:normal;font-display:block;}"
    )


def _cached_font_path() -> Path:
    return get_miho_dir("assets/fonts/goyang", "fonts/goyang") / "GoyangDeogyangB.ttf"


def _find_system_goyang_font() -> Path | None:
    env_path = os.environ.get("MIHO_GOYANG_FONT_PATH", "").strip()
    candidates = [Path(env_path)] if env_path else []
    candidates.extend(
        [
            Path.home() / "Library/Fonts/GOYANGDEOGYANG B.TTF",
            Path.home() / "Library/Fonts/GoyangDeogyangB.ttf",
            Path("/Library/Fonts/GOYANGDEOGYANG B.TTF"),
            Path("C:/Windows/Fonts/GOYANGDEOGYANG B.TTF"),
        ]
    )
    return next((path for path in candidates if path.exists()), None)


def _download_to_cache(target: Path) -> Path | None:
    try:
        with urlopen(GOYANG_DEOGYANG_URL, timeout=8) as response:
            data = response.read()
    except (OSError, URLError):
        return None
    try:
        with ZipFile(io.BytesIO(data)) as archive:
            name = _select_font_member(archive.namelist())
            if name is None:
                return None
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    except (OSError, ValueError):
        return None
    return target if target.exists() else None


def _select_font_member(names: list[str]) -> str | None:
    preferred = [name for name in names if "GOYANGDEOGYANG B" in name.upper()]
    if preferred:
        return preferred[0]
    fonts = [name for name in names if name.lower().endswith((".ttf", ".otf"))]
    return fonts[0] if fonts else None
