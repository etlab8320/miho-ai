"""Operational readiness checks for Governance OS."""

from __future__ import annotations

import importlib
import json

from plugins.governance_os.operations import run_readiness_check


def _reload_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants
    from agent import evolution

    importlib.reload(miho_constants)
    importlib.reload(evolution)
    return evolution


def test_readiness_passes_with_builtin_registry(tmp_path, monkeypatch) -> None:
    _reload_home(tmp_path, monkeypatch)

    report = run_readiness_check()

    assert report.ready
    assert report.registry_valid
    assert report.drills_passed
    assert report.simulator_passed
    assert report.council_probe_passed
    assert report.risk_probe_passed
    assert report.promotion_probe_passed
    assert report.promotion_tests_probe_passed
    assert report.retry_probe_passed
    assert report.retry_instruction_probe_passed
    assert report.transform_ledger_probe_passed
    assert report.final_delivery_probe_passed
    assert report.evolution_rollback_probe_passed
    assert report.hook_probe_passed
    assert report.manifest_probe_passed
    assert report.plugin_load_probe_passed
    assert report.auxiliary_instruction_probe_passed
    assert report.auxiliary_dispatcher_dataplane_probe_passed
    assert report.auxiliary_reviewer_dataplane_probe_passed
    assert report.domain_packs_passed
    assert report.quality_score == 100
    assert report.rollback_status == "builtin"
    assert report.failures == ()


def test_readiness_check_does_not_write_outcome_ledger(tmp_path, monkeypatch) -> None:
    evolution = _reload_home(tmp_path, monkeypatch)

    report = run_readiness_check()

    assert report.ready
    assert evolution.list_events(limit=5) == []


def test_readiness_flags_invalid_active_registry_pointer(tmp_path, monkeypatch) -> None:
    _reload_home(tmp_path, monkeypatch)
    active_path = tmp_path / "miho_home" / "governance_os" / "registry_active.json"
    active_path.parent.mkdir(parents=True)
    active_path.write_text(
        json.dumps({"schema_version": "governance-registry-active/v1", "snapshot_id": "missing"}),
        encoding="utf-8",
    )

    report = run_readiness_check()

    assert not report.ready
    assert report.quality_score < 100
    assert report.rollback_status == "invalid_active_snapshot"
    assert any("active registry" in failure for failure in report.failures)
