"""Operational readiness checks for Governance OS."""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone

from plugins.governance_os.operations import run_readiness_check
from plugins.governance_os.registry import load_builtin_registry, registry_from_mapping
from plugins.governance_os.cli import _readiness_payload


def _reload_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    monkeypatch.delenv("MIHO_GOVERNANCE_LIVE_SMOKE_RECEIPT", raising=False)

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
    assert report.final_delivery_retry_probe_passed
    assert report.self_harness_runtime_feedback_probe_passed
    assert report.evolution_rollback_probe_passed
    assert report.hook_probe_passed
    assert report.manifest_probe_passed
    assert report.plugin_load_probe_passed
    assert report.auxiliary_instruction_probe_passed
    assert report.auxiliary_dispatcher_dataplane_probe_passed
    assert report.auxiliary_reviewer_dataplane_probe_passed
    assert report.semantic_delivery_judge_dataplane_probe_passed
    assert report.routing_loop_probe_passed
    assert report.tool_contract_probe_passed
    assert report.academy_accuracy_probe_passed
    assert report.validation_loop_probe_passed
    assert report.validation_loop_smoke_mode == "live_safe"
    assert report.live_discord_verified is False
    assert report.full_system_ready is False
    assert report.full_system_score < 100
    assert report.domain_packs_passed
    assert report.quality_score == 100
    assert report.rollback_status == "builtin"
    assert report.failures == ()
    payload = _readiness_payload(report)
    assert payload["readiness_scope"] == "live_safe_preflight"
    assert payload["discord_artifact_preflight_ready"] is True
    assert payload["actual_discord_send_verified"] is False


def test_readiness_check_does_not_write_outcome_ledger(tmp_path, monkeypatch) -> None:
    evolution = _reload_home(tmp_path, monkeypatch)

    report = run_readiness_check()

    assert report.ready
    assert evolution.list_events(limit=5) == []


def test_readiness_uses_live_discord_receipt_for_full_system_score(tmp_path, monkeypatch) -> None:
    _reload_home(tmp_path, monkeypatch)
    artifact = tmp_path / "live-report.pdf"
    artifact.write_bytes(b"%PDF-1.4\n%%EOF\n")
    receipt_path = tmp_path / "miho_home" / "governance_os" / "discord_live_smoke_receipt.json"
    receipt_path.parent.mkdir(parents=True)
    receipt_path.write_text(
        json.dumps(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "live_gateway_receipt": {
                    "kind": "live_gateway_smoke",
                    "status": "passed",
                    "mode": "live",
                    "send_attempted": True,
                    "sent": True,
                    "evidence": "sent=True",
                },
                "attachment_receipt": {
                    "kind": "attachment_artifact_smoke",
                    "status": "passed",
                    "artifact_path": str(artifact),
                    "media_tag": f"MEDIA:`{artifact}`",
                    "evidence": "artifact delivered",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = run_readiness_check()

    assert report.ready
    assert report.quality_score == 100
    assert report.validation_loop_smoke_mode == "live"
    assert report.live_discord_verified is True
    assert report.full_system_ready is True
    assert report.full_system_score == 100


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


def test_readiness_flags_governance_plugin_disabled(tmp_path, monkeypatch) -> None:
    _reload_home(tmp_path, monkeypatch)
    config_path = tmp_path / "miho_home" / "config.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text("plugins:\n  disabled:\n    - governance_os\n", encoding="utf-8")

    report = run_readiness_check()

    assert not report.ready
    assert report.quality_score < 100
    assert not report.plugin_load_probe_passed
    assert any("plugin load probe" in failure for failure in report.failures)


def test_readiness_flags_active_registry_missing_routing_playbook(
    tmp_path,
    monkeypatch,
) -> None:
    _reload_home(tmp_path, monkeypatch)

    from plugins.governance_os.versioning import activate_registry_snapshot, snapshot_registry

    payload = load_builtin_registry().to_payload()
    payload["playbooks"].pop("designed_pdf_artifact")
    stale_registry = registry_from_mapping(payload)
    snapshot = snapshot_registry(
        stale_registry,
        reason="stale active routing snapshot",
        created_at="2026-06-26T00:00:00+00:00",
    )
    activate_registry_snapshot(snapshot.snapshot_id, reason="activate stale routing snapshot")

    report = run_readiness_check()

    assert not report.ready
    assert report.quality_score < 100
    assert not report.routing_loop_probe_passed
    assert any("routing loop probe" in failure for failure in report.failures)
