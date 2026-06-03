"""Helpers for academy router tests."""

from __future__ import annotations

import json
from typing import Any


def router_execute(
    tool: str,
    args: dict[str, Any],
    *,
    confidence: float = 0.96,
    **extra: Any,
) -> str:
    payload: dict[str, Any] = {
        "action": "execute",
        "domain": "academy_ops",
        "intent": "academy tool request",
        "evidence": ["academy operations context"],
        "ambiguous": False,
        "tool": tool,
        "args": args,
        "confidence": confidence,
    }
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def router_allow(*, confidence: float = 0.1, domain: str = "non_academy") -> str:
    return json.dumps(
        {
            "action": "allow",
            "domain": domain,
            "intent": "non academy conversation",
            "evidence": [],
            "ambiguous": domain != "academy_ops",
            "confidence": confidence,
        },
        ensure_ascii=False,
    )


def router_execute_plan(actions: list[dict[str, Any]], *, confidence: float = 0.96) -> str:
    return json.dumps(
        {
            "action": "execute",
            "domain": "academy_ops",
            "intent": "compound academy request",
            "evidence": ["academy operations context"],
            "ambiguous": False,
            "tool": "",
            "args": {},
            "actions": actions,
            "confidence": confidence,
        },
        ensure_ascii=False,
    )
