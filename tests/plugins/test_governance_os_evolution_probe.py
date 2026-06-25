"""Evolution rollback readiness probe tests for Governance OS."""

from __future__ import annotations


def test_evolution_rollback_probe_exercises_skill_and_harness_rollback() -> None:
    from plugins.governance_os.evolution_rollback_probe import run_evolution_rollback_probe

    assert run_evolution_rollback_probe()
