"""Data models for YouTube operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TranscriptSegment:
    start: float
    text: str


@dataclass(frozen=True)
class VideoMetadata:
    video_id: str
    title: str = ""
    channel: str = ""
    duration: str = ""


@dataclass
class SummaryResult:
    video_id: str
    canonical_url: str
    short_title: str
    metadata: VideoMetadata
    topic: str
    summary_lines: list[str]
    important_points: list[str]
    lessons: list[str]
    practical_takeaways: list[str]
    tags: list[str]
    coverage: dict[str, Any]
    card_image_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SummaryResult":
        raw_meta = data.get("metadata") or {}
        metadata = raw_meta if isinstance(raw_meta, VideoMetadata) else VideoMetadata(**raw_meta)
        return cls(
            video_id=str(data.get("video_id") or metadata.video_id),
            canonical_url=str(data.get("canonical_url") or ""),
            short_title=str(data.get("short_title") or ""),
            metadata=metadata,
            topic=str(data.get("topic") or ""),
            summary_lines=[str(item) for item in data.get("summary_lines") or []],
            important_points=[str(item) for item in data.get("important_points") or []],
            lessons=[str(item) for item in data.get("lessons") or []],
            practical_takeaways=[str(item) for item in data.get("practical_takeaways") or []],
            tags=[str(item) for item in data.get("tags") or []],
            coverage=dict(data.get("coverage") or {}),
            card_image_path=str(data.get("card_image_path") or ""),
        )


@dataclass(frozen=True)
class TranscriptBundle:
    metadata: VideoMetadata
    segments: list[TranscriptSegment] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        return " ".join(segment.text.strip() for segment in self.segments if segment.text.strip())
