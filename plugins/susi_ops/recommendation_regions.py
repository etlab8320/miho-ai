"""Region normalization for the Susi recommendation pipeline."""

from __future__ import annotations

import re
from typing import Any


_REGION_GROUPS = {
    "수도권": ["서울", "경기", "인천"],
    "충청": ["대전", "세종", "충남", "충북"],
    "강원": ["강원"],
    "영남": ["부산", "대구", "울산", "경남", "경북"],
    "경상": ["부산", "대구", "울산", "경남", "경북"],
    "호남": ["광주", "전남", "전북"],
    "전라": ["광주", "전남", "전북"],
    "제주": ["제주"],
}


def parse_regions(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = re.split(r"[,/·\s]+", str(value or ""))
    requested = [str(item).strip() for item in items if str(item).strip()]
    if any(item in ("전국", "전체") for item in requested):
        return []
    expanded: list[str] = []
    for item in requested:
        group = _REGION_GROUPS.get(item) or _REGION_GROUPS.get(item.rstrip("권"))
        expanded.extend(group if group else [item])
    return list(dict.fromkeys(expanded))


__all__ = ["parse_regions"]
