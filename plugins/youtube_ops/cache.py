"""Cache and title registry for YouTube summaries."""

from __future__ import annotations

import json
import re
from pathlib import Path

from miho_constants import get_miho_home
from utils import atomic_json_write

from .models import SummaryResult


class YouTubeCache:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_miho_home() / "youtube"
        self.summary_dir = self.root / "summaries"
        self.card_dir = self.root / "cards"
        self.title_index_path = self.root / "title_index.json"

    def load_summary(self, video_id: str) -> SummaryResult | None:
        path = self.summary_path(video_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        return SummaryResult.from_dict(data)

    def save_summary(self, summary: SummaryResult) -> SummaryResult:
        unique_title = self._unique_title(summary.short_title, summary.video_id)
        summary.short_title = unique_title
        self.summary_dir.mkdir(parents=True, exist_ok=True)
        atomic_json_write(self.summary_path(summary.video_id), summary.to_dict(), indent=2)
        self._remember_title(unique_title, summary.video_id)
        return summary

    def summary_path(self, video_id: str) -> Path:
        return self.summary_dir / f"{video_id}.json"

    def card_output_dir(self, video_id: str) -> Path:
        return self.card_dir / video_id

    def _unique_title(self, title: str, video_id: str) -> str:
        base = _compact_title(title) or video_id
        index = self._title_index()
        existing_video = index.get(base)
        if existing_video in {None, video_id}:
            return base
        suffix = video_id[-4:]
        candidate = f"{base}-{suffix}"
        counter = 2
        while candidate in index and index[candidate] != video_id:
            candidate = f"{base}-{suffix}-{counter}"
            counter += 1
        return candidate

    def _title_index(self) -> dict[str, str]:
        if not self.title_index_path.exists():
            return {}
        try:
            data = json.loads(self.title_index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}

    def _remember_title(self, title: str, video_id: str) -> None:
        index = self._title_index()
        index[title] = video_id
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_json_write(self.title_index_path, index, indent=2)


def _compact_title(title: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(title or "")).strip()
    cleaned = re.sub(r"[^\w가-힣 .:/+-]+", "", cleaned)
    return cleaned[:34].strip(" .:/+-")
