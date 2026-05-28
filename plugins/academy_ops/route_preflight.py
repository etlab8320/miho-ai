"""Optional deterministic preflight for academy natural routing."""

from __future__ import annotations

from typing import Any


def academy_preflight_decision(
    text: str,
    today: str,
    thread_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Defer natural PACA/Peak routing to the semantic router.

    Korean natural-language routing should not grow phrase dictionaries for
    every possible wording. The fast router model chooses the PACA/Peak tool;
    runtime code validates the returned tool contract before execution.
    """
    _ = (text, today, thread_context)
    return None
