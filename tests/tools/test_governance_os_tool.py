"""Tests for the Governance OS operations tool."""

from __future__ import annotations

import importlib
import json


def _load_tool(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants

    importlib.reload(miho_constants)
    import tools.governance_os_tool as tool

    importlib.reload(tool)
    return tool


def _json(raw: str) -> dict:
    return json.loads(raw)


def _receipt(name: str) -> dict[str, object]:
    from plugins.governance_os.deployment_preflight import build_verification_receipt

    return build_verification_receipt(
        name=name,
        command=f"pytest {name}",
        evidence=f"{name} passed",
    )


def test_governance_tool_status_reports_readiness(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(tool.governance_os_tool({"action": "status"}))

    from tools.registry import registry

    entry = registry.get_entry("governance_os")
    assert entry is not None
    assert entry.toolset == "governance"
    assert result["success"] is True
    assert result["readiness"]["ready"] is True
    assert result["readiness"]["quality_score"] == 100
    assert result["readiness"]["council_probe_passed"] is True
    assert result["readiness"]["risk_probe_passed"] is True
    assert result["readiness"]["promotion_probe_passed"] is True
    assert result["readiness"]["promotion_tests_probe_passed"] is True
    assert result["readiness"]["retry_probe_passed"] is True
    assert result["readiness"]["retry_instruction_probe_passed"] is True
    assert result["readiness"]["transform_ledger_probe_passed"] is True
    assert result["readiness"]["final_delivery_probe_passed"] is True
    assert result["readiness"]["evolution_rollback_probe_passed"] is True
    assert result["readiness"]["hook_probe_passed"] is True
    assert result["readiness"]["manifest_probe_passed"] is True
    assert result["readiness"]["plugin_load_probe_passed"] is True
    assert result["readiness"]["auxiliary_instruction_probe_passed"] is True
    assert result["readiness"]["auxiliary_dispatcher_dataplane_probe_passed"] is True
    assert result["readiness"]["auxiliary_reviewer_dataplane_probe_passed"] is True
    assert result["readiness"]["domain_packs_passed"] is True


def test_governance_tool_is_available_to_core_miho_toolsets(tmp_path, monkeypatch) -> None:
    _load_tool(tmp_path, monkeypatch)

    from toolsets import resolve_toolset

    assert "governance_os" in resolve_toolset("miho-cli")
    assert "governance_os" in resolve_toolset("miho-discord")


def test_governance_tool_drills_returns_cross_domain_results(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(tool.governance_os_tool({"action": "drills"}))

    assert result["success"] is True
    keys = {item["key"] for item in result["drills"]}
    assert "dev_destructive_git_block" in keys
    assert "discord_attachment_review_required" in keys
    assert result["passed"] is True


def test_governance_tool_simulate_returns_scenario_results(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(tool.governance_os_tool({"action": "simulate"}))

    assert result["success"] is True
    keys = {item["key"] for item in result["simulations"]}
    assert "discord_attachment_success" in keys
    assert "memory_privacy_missing_retry" in keys
    assert result["passed"] is True


def test_governance_tool_promotions_returns_repeated_failure_candidates(
    tmp_path,
    monkeypatch,
) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    from plugins.governance_os.ledger import OutcomeLedgerEntry, record_outcome

    for index in range(2):
        record_outcome(
            OutcomeLedgerEntry(
                request_id=f"req-promo-{index}",
                playbook_key="discord_attachment_delivery",
                tools_used=("media_delivery_contract",),
                review_status="fail",
                failures=("reviewer_missing",),
            )
        )

    result = _json(tool.governance_os_tool({"action": "promotions"}))

    assert result["success"] is True
    assert result["count"] == 1
    assert result["candidates"][0]["playbook_key"] == "discord_attachment_delivery"
    assert result["candidates"][0]["source_failure"] == "reviewer_missing"


def test_governance_tool_promote_activates_valid_candidate(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(
        tool.governance_os_tool(
            {
                "action": "promote",
                "playbook_key": "memory_policy_update",
                "promotion_action": "add_forbidden_tool",
                "value": "unsafe_memory_write",
                "source_failure": "privacy_leak",
                "recurrence_count": 2,
                "proposed_policy": "block unsafe memory writes",
                "evidence": ["event=1", "event=2"],
                "tests_required": ["tests/plugins/test_governance_os_simulator.py"],
                "test_receipts": [_receipt("tests/plugins/test_governance_os_simulator.py")],
                "rollback": "rollback active governance registry snapshot",
                "reason": "promote memory privacy guard",
            }
        )
    )

    from plugins.governance_os.versioning import load_runtime_registry

    runtime = load_runtime_registry()
    activation = result["activation"]
    assert result["success"] is True
    assert activation["snapshot_id"]
    assert activation["rollback_snapshot_id"]
    assert "unsafe_memory_write" in runtime.get_playbook(
        "memory_policy_update"
    ).forbidden_tools


def test_governance_tool_allows_promotion_rollback_without_extra_preflight(
    tmp_path,
    monkeypatch,
) -> None:
    tool = _load_tool(tmp_path, monkeypatch)
    promoted = _json(
        tool.governance_os_tool(
            {
                "action": "promote",
                "playbook_key": "memory_policy_update",
                "promotion_action": "add_forbidden_tool",
                "value": "unsafe_memory_write",
                "source_failure": "privacy_leak",
                "recurrence_count": 2,
                "proposed_policy": "block unsafe memory writes",
                "evidence": ["event=1", "event=2"],
                "tests_required": ["tests/plugins/test_governance_os_simulator.py"],
                "test_receipts": [_receipt("tests/plugins/test_governance_os_simulator.py")],
                "rollback": "rollback active governance registry snapshot",
                "reason": "promote memory privacy guard",
            }
        )
    )

    rollback = _json(
        tool.governance_os_tool(
            {
                "action": "rollback",
                "snapshot_id": promoted["activation"]["rollback_snapshot_id"],
                "reason": "rollback promoted memory privacy guard",
            }
        )
    )

    assert rollback["success"] is True
    assert rollback["activation"]["snapshot_id"] == promoted["activation"]["rollback_snapshot_id"]


def test_governance_tool_promote_requires_passed_tests(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(
        tool.governance_os_tool(
            {
                "action": "promote",
                "playbook_key": "memory_policy_update",
                "promotion_action": "add_forbidden_tool",
                "value": "unsafe_memory_write",
                "source_failure": "privacy_leak",
                "recurrence_count": 2,
                "proposed_policy": "block unsafe memory writes",
                "evidence": ["event=1", "event=2"],
                "tests_required": ["tests/plugins/test_governance_os_simulator.py"],
                "rollback": "rollback active governance registry snapshot",
            }
        )
    )

    assert result["success"] is False
    assert "검증 테스트" in result["error"]
    assert "tests_passed" not in result["error"]
    assert "test_receipts" not in result["error"]


def test_governance_tool_promote_rejects_string_test_receipts_with_plain_error(
    tmp_path,
    monkeypatch,
) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(
        tool.governance_os_tool(
            {
                "action": "promote",
                "playbook_key": "memory_policy_update",
                "promotion_action": "add_forbidden_tool",
                "value": "unsafe_memory_write",
                "source_failure": "privacy_leak",
                "recurrence_count": 2,
                "proposed_policy": "block unsafe memory writes",
                "evidence": ["event=1", "event=2"],
                "tests_required": ["tests/plugins/test_governance_os_simulator.py"],
                "test_receipts": ["tests/plugins/test_governance_os_simulator.py"],
                "rollback": "rollback active governance registry snapshot",
            }
        )
    )

    assert result["success"] is False
    assert "검증 테스트" in result["error"]
    assert "test receipts" not in result["error"]
    assert "test_receipts" not in result["error"]


def test_governance_tool_outcomes_returns_filtered_ledger_entries(
    tmp_path,
    monkeypatch,
) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    from plugins.governance_os.ledger import OutcomeLedgerEntry, record_outcome

    record_outcome(
        OutcomeLedgerEntry(
            request_id="req-tool-academy",
            playbook_key="academy_hakjong_report",
            review_status="pass",
        )
    )
    record_outcome(
        OutcomeLedgerEntry(
            request_id="req-tool-discord",
            playbook_key="discord_attachment_delivery",
            review_status="fail",
            failures=("reviewer_missing",),
        )
    )

    result = _json(
        tool.governance_os_tool(
            {
                "action": "outcomes",
                "playbook_key": "discord_attachment_delivery",
            }
        )
    )

    assert result["success"] is True
    assert result["count"] == 1
    assert result["outcomes"][0]["request_id"] == "req-tool-discord"
    assert result["outcomes"][0]["event_status"] == "failed"


def test_governance_tool_packs_returns_domain_pack_status(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(tool.governance_os_tool({"action": "packs"}))

    assert result["success"] is True
    assert result["passed"] is True
    domains = {item["domain"] for item in result["packs"]}
    assert {"academy", "dev", "research", "discord_ops", "memory"}.issubset(domains)


def test_governance_tool_preflight_blocks_missing_runtime_receipts(
    tmp_path,
    monkeypatch,
) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(
        tool.governance_os_tool(
            {
                "action": "preflight",
                "target": "gateway_restart",
                "rollback_plan": "",
            }
        )
    )

    assert result["success"] is False
    assert result["preflight"]["ready"] is False
    assert "테스트 영수증" in result["error"]
    assert "Traceback" not in result["error"]
    assert "tests_passed" not in result["error"]


def test_governance_tool_preflight_passes_structured_runtime_receipts(
    tmp_path,
    monkeypatch,
) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(
        tool.governance_os_tool(
            {
                "action": "preflight",
                "target": "gateway_restart",
                "test_receipts": [
                    _receipt("related_governance_suite"),
                    _receipt("static_checks"),
                ],
                "smoke_receipts": [
                    _receipt("governance_status"),
                    _receipt("discord_delivery"),
                ],
                "config_checks": [_receipt("gateway_service_definition")],
                "rollback_plan": "Rollback by reverting this diff and restarting the previous gateway process.",
            }
        )
    )

    assert result["success"] is True
    assert result["preflight"]["ready"] is True
    assert result["preflight"]["target"] == "gateway_restart"
    assert result["preflight"]["readiness_quality_score"] == 100


def test_governance_tool_snapshot_activate_and_rollback(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    snapshot = _json(tool.governance_os_tool({"action": "snapshot", "reason": "test"}))
    activate_blocked = _json(
        tool.governance_os_tool(
            {
                "action": "activate",
                "snapshot_id": snapshot["snapshot"]["snapshot_id"],
                "reason": "test activate",
            }
        )
    )
    rollback_blocked = _json(
        tool.governance_os_tool(
            {
                "action": "rollback",
                "snapshot_id": snapshot["snapshot"]["snapshot_id"],
                "reason": "test rollback",
            }
        )
    )
    activate = _json(
        tool.governance_os_tool(
            {
                "action": "activate",
                "snapshot_id": snapshot["snapshot"]["snapshot_id"],
                "reason": "test activate",
                "test_receipts": [
                    _receipt("related_governance_suite"),
                    _receipt("static_checks"),
                ],
                "smoke_receipts": [
                    _receipt("governance_status"),
                    _receipt("discord_delivery"),
                ],
                "config_checks": [_receipt("gateway_service_definition")],
                "rollback_plan": "Rollback by restoring the previous governance registry snapshot.",
            }
        )
    )
    rollback = _json(
        tool.governance_os_tool(
            {
                "action": "rollback",
                "snapshot_id": snapshot["snapshot"]["snapshot_id"],
                "reason": "test rollback",
                "test_receipts": [
                    _receipt("related_governance_suite"),
                    _receipt("static_checks"),
                ],
                "smoke_receipts": [
                    _receipt("governance_status"),
                    _receipt("discord_delivery"),
                ],
                "config_checks": [_receipt("gateway_service_definition")],
                "rollback_plan": "Rollback by restoring the previous governance registry snapshot.",
            }
        )
    )

    assert snapshot["success"] is True
    assert activate_blocked["success"] is False
    assert "검증" in activate_blocked["error"]
    assert rollback_blocked["success"] is False
    assert "검증" in rollback_blocked["error"]
    assert activate["success"] is True
    assert rollback["success"] is True
    assert activate["activation"]["snapshot_id"] == snapshot["snapshot"]["snapshot_id"]
    assert rollback["activation"]["snapshot_id"] == snapshot["snapshot"]["snapshot_id"]


def test_governance_tool_rejects_rollback_without_snapshot_id(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(tool.governance_os_tool({"action": "rollback"}))

    assert result["success"] is False
    assert "스냅샷" in result["error"]
    assert "snapshot_id" not in result["error"]


def test_governance_tool_hides_internal_exception_terms(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    def _raise_internal_error() -> str:
        raise RuntimeError("Traceback CORS pre_tool_call stack")

    monkeypatch.setattr(tool, "_status", _raise_internal_error)

    result = _json(tool.governance_os_tool({"action": "status"}))

    assert result["success"] is False
    assert "거버넌스" in result["error"]
    assert "Traceback" not in result["error"]
    assert "CORS" not in result["error"]
    assert "pre_tool_call" not in result["error"]


def test_governance_tool_unknown_action_uses_korean_plain_error(tmp_path, monkeypatch) -> None:
    tool = _load_tool(tmp_path, monkeypatch)

    result = _json(tool.governance_os_tool({"action": "unknown"}))

    assert result["success"] is False
    assert "알 수 없는" in result["error"]
    assert "Unknown action" not in result["error"]
