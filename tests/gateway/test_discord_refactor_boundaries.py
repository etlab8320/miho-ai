from __future__ import annotations

from pathlib import Path


DISCORD_DIR = Path(__file__).resolve().parents[2] / "plugins" / "platforms" / "discord"


def test_discord_runtime_files_stay_below_500_lines():
    runtime_files = sorted(DISCORD_DIR.glob("*.py"))

    oversized = {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in runtime_files
        if len(path.read_text(encoding="utf-8").splitlines()) > 500
    }

    assert oversized == {}


def test_discord_adapter_keeps_legacy_exports():
    from plugins.platforms.discord import adapter

    for name in (
        "DiscordAdapter",
        "VoiceReceiver",
        "ExecApprovalView",
        "SlashConfirmView",
        "UpdatePromptView",
        "ModelPickerView",
        "ClarifyChoiceView",
        "_derive_forum_thread_name",
        "_standalone_send",
        "interactive_setup",
        "_apply_yaml_config",
    ):
        assert hasattr(adapter, name), name
