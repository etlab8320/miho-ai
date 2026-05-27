"""Fast pre-gateway routing for explicit YouTube requests."""

from __future__ import annotations

from dataclasses import dataclass

from .ids import extract_video_id

IMAGE_MARKERS = ("이미지", "사진", "png", "카드")
REFRESH_MARKERS = ("새로", "다시", "재요약", "갱신")


@dataclass(frozen=True)
class YouTubePreflightDecision:
    args: dict[str, object]


def youtube_preflight_decision(text: str) -> YouTubePreflightDecision | None:
    """Return a fast-route decision for explicit YouTube URL/video-id input."""
    raw = str(text or "").strip()
    if not raw or extract_video_id(raw) is None:
        return None
    normalized = "".join(raw.lower().split())
    return YouTubePreflightDecision(
        args={
            "url": raw,
            "render_card": _contains_any(normalized, IMAGE_MARKERS),
            "force_refresh": _contains_any(normalized, REFRESH_MARKERS),
        }
    )


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker.lower() in text for marker in markers)
