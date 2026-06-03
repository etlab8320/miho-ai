from __future__ import annotations

import asyncio
import ctypes.util
import types
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


def test_discord_connect_handles_missing_opus_without_sys_name_error(monkeypatch):
    from plugins.platforms.discord import lifecycle_mixin

    class FakeOpus:
        @staticmethod
        def is_loaded():
            return False

    fake_discord = types.SimpleNamespace(opus=FakeOpus())
    fake_config = types.SimpleNamespace(token=None)
    fake_adapter = types.SimpleNamespace(config=fake_config, name="Discord")

    monkeypatch.setattr(lifecycle_mixin, "DISCORD_AVAILABLE", True)
    monkeypatch.setattr(lifecycle_mixin, "discord", fake_discord)
    monkeypatch.setattr(ctypes.util, "find_library", lambda _name: None)

    connected = asyncio.run(lifecycle_mixin.DiscordLifecycleMixin.connect(fake_adapter))

    assert connected is False
