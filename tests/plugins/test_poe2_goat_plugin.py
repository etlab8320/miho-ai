from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from plugins.poe2_goat import _poe2_pre_gateway_dispatch, _parse_poe2_request, _tool_handler, register


def test_parse_poe2_request_from_korean_text():
    req = _parse_poe2_request("poe2 50딥 소환 인퍼널리스트 The Raven's Flock")

    assert req is not None
    assert req["budget_div"] == 50
    assert req["archetype"] == "summoner"
    assert req["ascendancy"] == "Infernalist"
    assert req["core_item"] == "The Raven's Flock"


def test_tool_handler_invokes_project_cli(monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="# Report\n", stderr="")

    monkeypatch.setattr("plugins.poe2_goat.subprocess.run", fake_run)

    result = _tool_handler({"archetype": "summoner", "ascendancy": "Infernalist", "budget_div": 50, "format": "markdown"})

    assert result == "# Report\n"
    assert "poe2goat.cli" in calls[0]
    assert "--ascendancy" in calls[0]


@pytest.mark.asyncio
async def test_pre_gateway_responds_for_poe2_build_request(monkeypatch):
    async def fake_to_thread(fn, args):
        return "# PoE2 GOAT Build Report\n"

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    event = SimpleNamespace(text="poe2 50딥 소환 인퍼널리스트")

    result = await _poe2_pre_gateway_dispatch(event=event)

    assert result["action"] == "respond"
    assert result["route"] == "poe2_goat"
    assert "PoE2 GOAT" in result["text"]


def test_register_adds_tool_and_hook():
    calls = {"tools": [], "hooks": []}

    class Ctx:
        def register_tool(self, **kwargs):
            calls["tools"].append(kwargs)

        def register_hook(self, name, handler):
            calls["hooks"].append((name, handler))

    register(Ctx())

    assert calls["tools"][0]["name"] == "poe2_goat_build"
    assert calls["hooks"][0][0] == "pre_gateway_dispatch"
