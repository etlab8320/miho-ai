"""Small in-memory rate limiter for academy login attempts."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


WINDOW_SECONDS = 10 * 60
MAX_FAILURES = 8


@dataclass
class AttemptBucket:
    failures: list[float] = field(default_factory=list)


_BUCKETS: dict[str, AttemptBucket] = {}


def is_limited(key: str, *, now: float | None = None) -> bool:
    bucket = _bucket_for(key, now=now)
    return len(bucket.failures) >= MAX_FAILURES


def record_failure(key: str, *, now: float | None = None) -> None:
    current = now or time.time()
    bucket = _bucket_for(key, now=current)
    bucket.failures.append(current)


def record_success(key: str) -> None:
    _BUCKETS.pop(_normalize_key(key), None)


def _bucket_for(key: str, *, now: float | None = None) -> AttemptBucket:
    current = now or time.time()
    clean = _normalize_key(key)
    cutoff = current - WINDOW_SECONDS
    bucket = _BUCKETS.setdefault(clean, AttemptBucket())
    bucket.failures = [item for item in bucket.failures if item >= cutoff]
    return bucket


def _normalize_key(key: str) -> str:
    return key.strip() or "unknown"
