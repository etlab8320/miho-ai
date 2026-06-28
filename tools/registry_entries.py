"""Tool registry entry and availability-cache helpers."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any


class ToolEntry:
    """Metadata for a single registered tool."""

    __slots__ = (
        "name",
        "toolset",
        "schema",
        "handler",
        "check_fn",
        "requires_env",
        "is_async",
        "description",
        "emoji",
        "max_result_size_chars",
        "dynamic_schema_overrides",
    )

    def __init__(
        self,
        name: str,
        toolset: str,
        schema: dict[str, Any],
        handler: Callable,
        check_fn: Callable | None,
        requires_env: list[str],
        is_async: bool,
        description: str,
        emoji: str,
        max_result_size_chars: int | float | None = None,
        dynamic_schema_overrides: Callable | None = None,
    ) -> None:
        self.name = name
        self.toolset = toolset
        self.schema = schema
        self.handler = handler
        self.check_fn = check_fn
        self.requires_env = requires_env
        self.is_async = is_async
        self.description = description
        self.emoji = emoji
        self.max_result_size_chars = max_result_size_chars
        self.dynamic_schema_overrides = dynamic_schema_overrides


_CHECK_FN_TTL_SECONDS = 30.0
_check_fn_cache: dict[Callable, tuple[float, bool]] = {}
_check_fn_cache_lock = threading.Lock()


def _check_fn_cached(fn: Callable) -> bool:
    """Return bool(fn()), TTL-cached across calls."""
    now = time.monotonic()
    with _check_fn_cache_lock:
        cached = _check_fn_cache.get(fn)
        if cached is not None:
            ts, value = cached
            if now - ts < _CHECK_FN_TTL_SECONDS:
                return value
    try:
        value = bool(fn())
    except Exception:
        value = False
    with _check_fn_cache_lock:
        _check_fn_cache[fn] = (now, value)
    return value


def invalidate_check_fn_cache() -> None:
    """Drop cached ``check_fn`` results after config changes."""
    with _check_fn_cache_lock:
        _check_fn_cache.clear()
