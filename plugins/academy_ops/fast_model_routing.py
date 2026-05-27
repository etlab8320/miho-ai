"""Gateway model routing for bound academy sessions."""

from __future__ import annotations

from typing import Any

from .commentary_config import COMMENTARY_PROVIDER
from .codex_model_policy import session_model


def route_bound_academy_session_to_fast_model(*, gateway: Any, event: Any, has_binding: bool) -> bool:
    if not has_binding or gateway is None or event is None:
        return False
    text = str(getattr(event, "text", "") or "").strip()
    if text.startswith("/"):
        return False
    source = getattr(event, "source", None)
    session_key_fn = getattr(gateway, "_session_key_for_source", None)
    overrides = getattr(gateway, "_session_model_overrides", None)
    if source is None or not callable(session_key_fn) or not isinstance(overrides, dict):
        return False
    session_key = session_key_fn(source)
    if not session_key:
        return False
    desired = {"model": session_model(), "provider": COMMENTARY_PROVIDER}
    current = overrides.get(session_key) or {}
    if current.get("model") == desired["model"] and current.get("provider") == desired["provider"]:
        return False
    overrides[session_key] = desired
    evict = getattr(gateway, "_evict_cached_agent", None)
    if callable(evict):
        evict(session_key)
    return True
