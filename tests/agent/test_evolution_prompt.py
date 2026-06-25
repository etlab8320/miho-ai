"""Tests for injecting promoted Evolution OS harness rules."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def prompt_env(monkeypatch, tmp_path):
    home = tmp_path / ".miho"
    home.mkdir()
    (home / "skills").mkdir()
    monkeypatch.setenv("MIHO_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    import miho_constants
    importlib.reload(miho_constants)
    from agent import evolution
    importlib.reload(evolution)
    import agent.system_prompt as system_prompt
    importlib.reload(system_prompt)
    return {"home": home, "evolution": evolution, "system_prompt": system_prompt}


def test_build_harness_rules_prompt_contains_active_rules(prompt_env):
    ev = prompt_env["evolution"]
    system_prompt = prompt_env["system_prompt"]
    proposal = ev.record_event(
        kind="proposal",
        title="Harness rule: inspect before retry",
        summary="If the same command fails twice, inspect before retrying.",
        evidence="failure traces",
        status="validated",
    )
    ev.promote_proposal(proposal["id"])

    prompt = system_prompt.build_evolution_harness_prompt()

    assert "Miho Evolution Harness Rules" in prompt
    assert "inspect before retrying" in prompt
