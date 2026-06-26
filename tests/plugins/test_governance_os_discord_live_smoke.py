"""Discord live-smoke receipt contracts for Governance OS validation."""

from __future__ import annotations

import json

from plugins.governance_os.discord_live_smoke import build_discord_delivery_smoke


def test_discord_live_safe_smoke_builds_validation_receipts(tmp_path) -> None:
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"%PDF-1.4\n%%EOF\n")

    smoke = build_discord_delivery_smoke(
        artifact_path=str(artifact),
        mode="live_safe",
        gateway_running=lambda: True,
        media_contract=lambda _args: json.dumps(
            {
                "success": True,
                "artifact_path": str(artifact),
                "media_tag": f"MEDIA:`{artifact}`",
                "delivery_text": f"검증 파일\nMEDIA:`{artifact}`",
            },
            ensure_ascii=False,
        ),
    )

    assert smoke.ready
    assert smoke.preflight_receipt["name"] == "discord_delivery"
    assert smoke.preflight_receipt["status"] == "passed"
    assert smoke.live_gateway_receipt["kind"] == "live_gateway_smoke"
    assert smoke.live_gateway_receipt["mode"] == "live_safe"
    assert smoke.attachment_receipt["kind"] == "attachment_artifact_smoke"
    assert smoke.attachment_receipt["media_tag"] == f"MEDIA:`{artifact}`"
    assert "token" not in smoke.preflight_receipt["evidence"].lower()


def test_discord_live_smoke_sends_when_target_and_sender_are_explicit(tmp_path) -> None:
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"%PDF-1.4\n%%EOF\n")
    sent: list[dict[str, str]] = []

    def sender(target: str, message: str) -> dict[str, object]:
        sent.append({"target": target, "message": message})
        return {"success": True, "message_id": "discord-live-smoke-1"}

    smoke = build_discord_delivery_smoke(
        artifact_path=str(artifact),
        mode="live",
        target="discord:123:456",
        gateway_running=lambda: True,
        media_contract=lambda _args: json.dumps(
            {
                "success": True,
                "artifact_path": str(artifact),
                "media_tag": f"MEDIA:`{artifact}`",
                "delivery_text": f"검증 파일\nMEDIA:`{artifact}`",
            },
            ensure_ascii=False,
        ),
        sender=sender,
    )

    assert smoke.ready
    assert smoke.live_gateway_receipt["mode"] == "live"
    assert smoke.live_gateway_receipt["send_attempted"] is True
    assert smoke.live_gateway_receipt["sent"] is True
    assert smoke.preflight_receipt["status"] == "passed"
    assert sent == [
        {
            "target": "discord:123:456",
            "message": f"검증 파일\nMEDIA:`{artifact}`",
        }
    ]


def test_discord_live_smoke_fails_closed_without_gateway(tmp_path) -> None:
    artifact = tmp_path / "report.pdf"
    artifact.write_bytes(b"%PDF-1.4\n%%EOF\n")

    smoke = build_discord_delivery_smoke(
        artifact_path=str(artifact),
        mode="live_safe",
        gateway_running=lambda: False,
        media_contract=lambda _args: "{}",
    )

    assert not smoke.ready
    assert smoke.preflight_receipt["status"] == "failed"
    assert "gateway_not_running" in smoke.failures
