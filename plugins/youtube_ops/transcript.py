"""YouTube metadata and transcript fetchers."""

from __future__ import annotations

import json
import re
import html
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

from .ids import canonical_url
from .models import TranscriptSegment, VideoMetadata

OEMBED_TIMEOUT_SECONDS = 5.0


class YouTubeFetchError(RuntimeError):
    pass


def fetch_video_metadata(video_id: str) -> VideoMetadata:
    endpoint = "https://www.youtube.com/oembed?format=json&url=" + quote(
        canonical_url(video_id), safe=""
    )
    try:
        with urlopen(endpoint, timeout=OEMBED_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return VideoMetadata(video_id=video_id)
    if not isinstance(payload, dict):
        return VideoMetadata(video_id=video_id)
    return VideoMetadata(
        video_id=video_id,
        title=_clean(payload.get("title")),
        channel=_clean(payload.get("author_name")),
    )


def fetch_transcript(video_id: str, languages: list[str] | None = None) -> list[TranscriptSegment]:
    errors: list[str] = []
    try:
        return _fetch_with_transcript_api(video_id, languages or ["ko", "ko-KR", "en"])
    except YouTubeFetchError as exc:
        errors.append(str(exc))
    try:
        fallback = _fetch_with_ytdlp(video_id)
    except YouTubeFetchError as exc:
        errors.append(str(exc))
        fallback = []
    if fallback:
        return fallback
    raise YouTubeFetchError("; ".join(_dedupe_errors(errors)) or "유튜브 자막을 가져오지 못했어.")


def _fetch_with_transcript_api(video_id: str, languages: list[str]) -> list[TranscriptSegment]:
    _ensure_transcript_dependency()
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:
        raise YouTubeFetchError(
            "youtube-transcript-api가 설치되어 있지 않아. miho-agent[youtube] extra가 필요해."
        ) from exc
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=languages)
    except Exception as exc:
        raise YouTubeFetchError(_plain_error(exc)) from exc
    return [TranscriptSegment(start=float(item.start), text=str(item.text)) for item in fetched]


def _ensure_transcript_dependency() -> None:
    try:
        from tools.lazy_deps import FeatureUnavailable, ensure
    except ImportError:
        return
    try:
        ensure("skill.youtube")
    except FeatureUnavailable as exc:
        raise YouTubeFetchError("유튜브 자막 도구 준비에 실패했어. 설치 상태를 확인해야 해.") from exc


def _fetch_with_ytdlp(video_id: str) -> list[TranscriptSegment]:
    url = canonical_url(video_id)
    command = ["yt-dlp", "--skip-download", "--dump-json", url]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise YouTubeFetchError("yt-dlp 자막 fallback을 실행하지 못했어.") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "yt-dlp 실패").strip()
        raise YouTubeFetchError(_plain_error(RuntimeError(detail)))
    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise YouTubeFetchError("yt-dlp 메타데이터를 읽지 못했어.") from exc
    caption_url = _select_caption_url(metadata)
    if not caption_url:
        raise YouTubeFetchError("yt-dlp에서도 사용할 수 있는 자막을 찾지 못했어.")
    try:
        with urlopen(caption_url, timeout=10) as response:
            vtt = response.read().decode("utf-8", errors="replace")
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise YouTubeFetchError("yt-dlp 자막 파일을 내려받지 못했어.") from exc
    return parse_vtt_transcript(vtt)


def parse_vtt_transcript(vtt: str) -> list[TranscriptSegment]:
    segments: list[TranscriptSegment] = []
    current_start: float | None = None
    buffer: list[str] = []
    previous_text = ""
    for raw_line in vtt.splitlines():
        line = raw_line.strip()
        if not line or line == "WEBVTT" or line.startswith(("Kind:", "Language:", "NOTE")):
            _flush_segment(segments, current_start, buffer, previous_text)
            if buffer:
                previous_text = _clean_caption_text(" ".join(buffer))
            buffer = []
            current_start = None
            continue
        if "-->" in line:
            _flush_segment(segments, current_start, buffer, previous_text)
            if buffer:
                previous_text = _clean_caption_text(" ".join(buffer))
            buffer = []
            current_start = _parse_vtt_time(line.split("-->", 1)[0].strip())
            continue
        if line.isdigit() or line.startswith(("STYLE", "REGION")):
            continue
        buffer.append(line)
    _flush_segment(segments, current_start, buffer, previous_text)
    return _dedupe_segments(segments)


def _select_caption_url(metadata: dict[str, object]) -> str:
    for group_name in ("subtitles", "automatic_captions"):
        group = metadata.get(group_name)
        if not isinstance(group, dict):
            continue
        for lang in ("ko-orig", "ko", "ko-KR", "en"):
            entries = group.get(lang)
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and str(entry.get("ext") or "").lower() == "vtt":
                    return str(entry.get("url") or "")
    return ""


def _flush_segment(
    segments: list[TranscriptSegment],
    start: float | None,
    buffer: list[str],
    previous_text: str,
) -> None:
    if start is None or not buffer:
        return
    text = _clean_caption_text(" ".join(buffer))
    if text and text != previous_text:
        segments.append(TranscriptSegment(start=start, text=text))


def _clean_caption_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_vtt_time(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    try:
        if len(parts) == 3:
            hours, minutes, seconds = parts
            return (int(hours) * 3600) + (int(minutes) * 60) + float(seconds)
        if len(parts) == 2:
            minutes, seconds = parts
            return (int(minutes) * 60) + float(seconds)
    except ValueError:
        return 0.0
    return 0.0


def _dedupe_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    result: list[TranscriptSegment] = []
    previous = ""
    for segment in segments:
        key = re.sub(r"\s+", "", segment.text).lower()
        if key and key != previous:
            result.append(segment)
            previous = key
    return result


def _clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _plain_error(exc: Exception) -> str:
    text = str(exc)
    lowered = text.lower()
    if "disabled" in lowered:
        return "이 영상은 자막이 꺼져 있어."
    if "no transcript" in lowered:
        return "사용 가능한 자막을 찾지 못했어."
    if (
        "unavailable" in lowered
        or "private" in lowered
        or "video unavailable" in lowered
        or "no longer available" in lowered
    ):
        return "비공개이거나 삭제된 영상 같아."
    return text[:300]


def _dedupe_errors(errors: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for error in errors:
        key = re.sub(r"\s+", " ", error).strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result
