"""Registry versioning contract tests for Governance OS."""

from __future__ import annotations

import importlib

from plugins.governance_os.registry import load_builtin_registry, registry_from_mapping


def _reload_evolution_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants
    from agent import evolution

    importlib.reload(miho_constants)
    importlib.reload(evolution)
    return evolution


def test_registry_snapshot_activation_roundtrips_runtime_registry(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    from plugins.governance_os.versioning import (
        activate_registry_snapshot,
        load_runtime_registry,
        snapshot_registry,
    )

    registry = load_builtin_registry()
    snapshot = snapshot_registry(
        registry,
        reason="test snapshot",
        created_at="2026-06-25T00:00:00+00:00",
    )
    activation = activate_registry_snapshot(snapshot.snapshot_id, reason="test activate")

    runtime = load_runtime_registry()

    assert snapshot.path.exists()
    assert activation.snapshot_id == snapshot.snapshot_id
    assert runtime.fingerprint == registry.fingerprint
    assert runtime.get_playbook("academy_hakjong_report").required_tools == (
        "academy_hakjong_report_package",
    )
    latest = evolution.list_events(limit=1)[0]
    assert latest["kind"] == "promotion"
    assert latest["metadata"]["governance_registry_activation"]["snapshot_id"] == snapshot.snapshot_id


def test_registry_rollback_restores_previous_active_snapshot(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    from plugins.governance_os.versioning import (
        activate_registry_snapshot,
        load_runtime_registry,
        rollback_registry_snapshot,
        snapshot_registry,
    )

    stable = load_builtin_registry()
    relaxed_payload = stable.to_payload()
    relaxed_payload["playbooks"]["academy_hakjong_report"]["forbidden_tools"].remove("write_file")
    relaxed = registry_from_mapping(relaxed_payload)

    stable_snapshot = snapshot_registry(
        stable,
        reason="stable",
        created_at="2026-06-25T00:00:00+00:00",
    )
    relaxed_snapshot = snapshot_registry(
        relaxed,
        reason="candidate",
        created_at="2026-06-25T00:00:01+00:00",
    )

    activate_registry_snapshot(relaxed_snapshot.snapshot_id, reason="candidate activate")
    assert "write_file" not in load_runtime_registry().get_playbook(
        "academy_hakjong_report"
    ).forbidden_tools

    rollback = rollback_registry_snapshot(stable_snapshot.snapshot_id, reason="restore stable")
    runtime = load_runtime_registry()

    assert rollback.snapshot_id == stable_snapshot.snapshot_id
    assert "write_file" in runtime.get_playbook("academy_hakjong_report").forbidden_tools
    latest = evolution.list_events(limit=1)[0]
    assert latest["kind"] == "rollback"
    assert latest["metadata"]["governance_registry_rollback"]["snapshot_id"] == stable_snapshot.snapshot_id


def test_pre_tool_guard_uses_active_registry_snapshot(tmp_path, monkeypatch) -> None:
    _reload_evolution_home(tmp_path, monkeypatch)

    from plugins.governance_os.guard import governance_pre_tool_call
    from plugins.governance_os.versioning import activate_registry_snapshot, snapshot_registry

    stable = load_builtin_registry()
    relaxed_payload = stable.to_payload()
    relaxed_payload["playbooks"]["academy_hakjong_report"]["forbidden_tools"].remove("write_file")
    relaxed = registry_from_mapping(relaxed_payload)
    snapshot = snapshot_registry(
        relaxed,
        reason="relaxed guard test",
        created_at="2026-06-25T00:00:02+00:00",
    )
    activate_registry_snapshot(snapshot.snapshot_id, reason="activate relaxed guard test")

    result = governance_pre_tool_call(
        tool_name="write_file",
        args={
            "path": "report.pdf",
            "content": "가은이 학종 리포트 PDF를 직접 만들어줘",
        },
    )

    assert result is None
