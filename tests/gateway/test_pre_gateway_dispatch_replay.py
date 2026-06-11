"""Replay fixture coverage for gateway pre-dispatch routing decisions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from gateway.pre_dispatch import resolve_pre_gateway_dispatch


_FIXTURE = Path(__file__).parents[1] / "fixtures" / "pre_gateway_routing_replay.json"


def _cases() -> list[dict[str, Any]]:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["name"])
def test_pre_gateway_dispatch_replay_cases(case: dict[str, Any]) -> None:
    decision = resolve_pre_gateway_dispatch(case["candidates"])
    expected = case["expected"]

    assert decision.action == expected["action"]
    assert decision.route == expected["route"]
    assert decision.reason == expected["reason"]
    assert decision.intent == expected["intent"]
    assert decision.required_tool == expected["required_tool"]
    assert len(decision.candidates) == len(case["candidates"])
