"""Shared academy brand assets for HTML image renderers."""

from __future__ import annotations

import base64
import os
from pathlib import Path

from miho_constants import get_miho_home

from .context import current_discord_user_id


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
# Magic-byte signatures keyed by the extension we persist the logo under.
# Limited to the raster formats the renderer MIME map can inline.
_IMAGE_SIGNATURES: tuple[tuple[str, bytes], ...] = (
    (".png", b"\x89PNG\r\n\x1a\n"),
    (".jpg", b"\xff\xd8\xff"),
    (".webp", b"RIFF"),
)
# Hard cap on a stored academy logo (5 MB). Logos are small header stamps;
# this keeps the base64-inlined data URL well within renderer limits.
MAX_LOGO_BYTES = 5 * 1024 * 1024


def academy_logo_store_dir() -> Path:
    return get_miho_home() / "academy_logos"


def stored_academy_logo_path(academy_id: str) -> Path | None:
    """Return the persisted logo for an academy, or None when none is set."""
    academy_id = str(academy_id or "").strip()
    if not academy_id:
        return None
    store = academy_logo_store_dir()
    for ext in _IMAGE_MIME_TYPES:
        candidate = store / f"{academy_id}{ext}"
        if candidate.exists():
            return candidate
    return None


def academy_brand_logo_path(academy_id: str | None = None) -> Path | None:
    """Resolve the brand logo path with academy-first priority.

    Order: (a) the bound academy's stored logo, (b) the ``MIHO_ACADEMY_BRAND_LOGO_PATH``
    env override, (c) the bundled stamp. ``academy_id`` defaults to the academy
    bound to the current Discord user so existing no-arg call sites become
    academy-aware without changes; pass an explicit id to override resolution.
    """
    resolved_id = academy_id if academy_id is not None else _current_academy_id()
    stored = stored_academy_logo_path(resolved_id) if resolved_id else None
    if stored is not None:
        return stored
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


def save_academy_logo(academy_id: str, data: bytes) -> Path:
    """Persist ``data`` as the academy's brand logo, replacing any prior one.

    Validates that ``data`` is a real image via magic bytes and stores it under
    ``<MIHO_HOME>/academy_logos/<academy_id><ext>``. Raises ``ValueError`` when
    the bytes are not a supported image or exceed ``MAX_LOGO_BYTES``.
    """
    academy_id = str(academy_id or "").strip()
    if not academy_id:
        raise ValueError("academy_id is required")
    if not data:
        raise ValueError("로고 이미지 데이터가 비어 있어.")
    if len(data) > MAX_LOGO_BYTES:
        raise ValueError(
            f"로고 이미지가 너무 커. 최대 {MAX_LOGO_BYTES // (1024 * 1024)}MB까지 가능해."
        )
    ext = _detect_logo_ext(data)
    if ext is None:
        raise ValueError("PNG, JPG, WEBP, GIF 형식의 실제 이미지 파일만 로고로 쓸 수 있어.")
    delete_academy_logo(academy_id)
    store = academy_logo_store_dir()
    store.mkdir(parents=True, exist_ok=True)
    target = store / f"{academy_id}{ext}"
    target.write_bytes(data)
    return target


def delete_academy_logo(academy_id: str) -> bool:
    """Remove any stored logo for the academy. Returns True when one existed."""
    academy_id = str(academy_id or "").strip()
    if not academy_id:
        return False
    removed = False
    store = academy_logo_store_dir()
    for ext in _IMAGE_MIME_TYPES:
        candidate = store / f"{academy_id}{ext}"
        if candidate.exists():
            candidate.unlink()
            removed = True
    return removed


def _detect_logo_ext(data: bytes) -> str | None:
    head = data[:16]
    for ext, signature in _IMAGE_SIGNATURES:
        if ext == ".webp":
            if len(data) >= 12 and head[:4] == b"RIFF" and data[8:12] == b"WEBP":
                return ext
            continue
        if head.startswith(signature):
            return ext
    return None


def _current_academy_id() -> str:
    discord_user_id = current_discord_user_id()
    if not discord_user_id:
        return ""
    try:
        from .auth_store import get_binding

        binding = get_binding(discord_user_id)
    except Exception:
        return ""
    return binding.academy_id if binding is not None else ""


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
