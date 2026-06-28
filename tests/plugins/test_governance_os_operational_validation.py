"""Operational validation report tests for Governance OS."""

from __future__ import annotations

import json

from plugins.governance_os import operational_validation


class _Readiness:
    ready = True
    academy_accuracy_probe_passed = True
    live_discord_verified = False
    failures = ()


def test_operational_validation_combines_academy_and_discord_smoke(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    monkeypatch.setattr(operational_validation, "run_readiness_check", lambda: _Readiness())
    monkeypatch.setattr("gateway.status.is_gateway_running", lambda: True)
    monkeypatch.setattr(
        "tools.media_delivery_contract_tool.media_delivery_contract_tool",
        lambda args: json.dumps(
            {
                "success": True,
                "artifact_path": args["artifact_path"],
                "media_tag": f"MEDIA:`{args['artifact_path']}`",
                "delivery_text": "검증 파일",
            },
            ensure_ascii=False,
        ),
    )

    report = operational_validation.build_operational_validation_report(mode="live_safe")

    assert report.ready
    assert report.readiness_ready
    assert report.academy_accuracy_ready
    assert report.discord_delivery_ready
    assert report.mode == "live_safe"
    assert report.receipts["live_gateway"]["mode"] == "live_safe"
    payload = report.to_payload()
    assert payload["gateway_process_ready"] is True
    assert payload["discord_artifact_preflight_ready"] is True
    assert payload["actual_discord_send_verified"] is False
    assert payload["live_discord_verified"] is False


def test_operational_validation_fails_when_academy_probe_fails(tmp_path, monkeypatch) -> None:
    class _FailingReadiness:
        ready = True
        academy_accuracy_probe_passed = False
        live_discord_verified = False
        failures = ()

    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    monkeypatch.setattr(operational_validation, "run_readiness_check", lambda: _FailingReadiness())
    monkeypatch.setattr("gateway.status.is_gateway_running", lambda: True)
    monkeypatch.setattr(
        "tools.media_delivery_contract_tool.media_delivery_contract_tool",
        lambda args: json.dumps(
            {
                "success": True,
                "artifact_path": args["artifact_path"],
                "media_tag": f"MEDIA:`{args['artifact_path']}`",
                "delivery_text": "검증 파일",
            },
            ensure_ascii=False,
        ),
    )

    report = operational_validation.build_operational_validation_report(mode="live_safe")

    assert not report.ready
    assert not report.academy_accuracy_ready
    assert "academy_accuracy_probe_failed" in report.failures


def test_operational_validation_live_uses_default_send_message_sender(tmp_path, monkeypatch) -> None:
    sent: list[dict[str, str]] = []

    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    monkeypatch.setattr(operational_validation, "run_readiness_check", lambda: _Readiness())
    monkeypatch.setattr("gateway.status.is_gateway_running", lambda: True)
    monkeypatch.setattr("miho_cli.send_cmd._load_miho_env", lambda: None)
    monkeypatch.setattr(
        "tools.media_delivery_contract_tool.media_delivery_contract_tool",
        lambda args: json.dumps(
            {
                "success": True,
                "artifact_path": args["artifact_path"],
                "media_tag": f"MEDIA:`{args['artifact_path']}`",
                "delivery_text": "검증 파일",
            },
            ensure_ascii=False,
        ),
    )

    def fake_send_message(args: dict[str, str]) -> str:
        sent.append(args)
        return json.dumps({"success": True, "message_id": "smoke-1"})

    monkeypatch.setattr("tools.send_message_tool.send_message_tool", fake_send_message)

    report = operational_validation.build_operational_validation_report(
        mode="live",
        target="discord:123:456",
    )

    assert report.ready
    assert report.actual_discord_send_verified is True
    assert report.receipts["live_gateway"]["sent"] is True
    assert sent == [
        {
            "action": "send",
            "target": "discord:123:456",
            "message": "검증 파일",
        }
    ]


def test_operational_validation_persists_successful_live_smoke_receipt(tmp_path, monkeypatch) -> None:
    home = tmp_path / "miho_home"
    receipt_path = home / "governance_os" / "discord_live_smoke_receipt.json"

    monkeypatch.setenv("MIHO_HOME", str(home))
    monkeypatch.setattr(operational_validation, "run_readiness_check", lambda: _Readiness())
    monkeypatch.setattr("gateway.status.is_gateway_running", lambda: True)
    monkeypatch.setattr("miho_cli.send_cmd._load_miho_env", lambda: None)
    monkeypatch.setattr(
        "tools.media_delivery_contract_tool.media_delivery_contract_tool",
        lambda args: json.dumps(
            {
                "success": True,
                "artifact_path": args["artifact_path"],
                "media_tag": f"MEDIA:`{args['artifact_path']}`",
                "delivery_text": "검증 파일",
            },
            ensure_ascii=False,
        ),
    )
    monkeypatch.setattr(
        "tools.send_message_tool.send_message_tool",
        lambda _args: json.dumps({"success": True, "message_id": "smoke-1"}),
    )

    report = operational_validation.build_operational_validation_report(
        mode="live",
        target="discord:123:456",
    )

    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert report.ready
    assert payload["live_gateway_receipt"]["mode"] == "live"
    assert payload["live_gateway_receipt"]["sent"] is True
    assert payload["attachment_receipt"]["kind"] == "attachment_artifact_smoke"
    assert payload["created_at"]
