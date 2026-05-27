"""YouTube URL and video ID helpers."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def extract_video_id(value: str) -> str | None:
    raw = str(value or "").strip()
    if VIDEO_ID_RE.fullmatch(raw):
        return raw
    for raw_url in re.findall(r"https?://\S+", raw):
        parsed = urlparse(raw_url.rstrip(")].,>"))
        host = parsed.netloc.lower()
        if host not in YOUTUBE_HOSTS:
            continue
        if host == "youtu.be":
            candidate = parsed.path.strip("/").split("/")[0]
            return candidate if VIDEO_ID_RE.fullmatch(candidate or "") else None
        query_id = parse_qs(parsed.query).get("v", [""])[0]
        if VIDEO_ID_RE.fullmatch(query_id or ""):
            return query_id
        parts = [part for part in parsed.path.split("/") if part]
        for marker in ("shorts", "embed", "live"):
            if marker not in parts:
                continue
            idx = parts.index(marker) + 1
            if idx < len(parts) and VIDEO_ID_RE.fullmatch(parts[idx]):
                return parts[idx]
    return None


def canonical_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"
