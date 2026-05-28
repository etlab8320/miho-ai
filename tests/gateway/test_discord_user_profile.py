from __future__ import annotations

import json
from unittest.mock import patch

from gateway.config import Platform
from gateway.discord_workspace import record_turn_and_build_prompt
from gateway.session import SessionSource
from gateway.session_context import clear_session_vars, set_session_vars


def _source(user_id: str = "user-1") -> SessionSource:
    return SessionSource(
        platform=Platform.DISCORD,
        chat_id="channel-7",
        chat_name="general",
        chat_type="group",
        user_id=user_id,
        user_name="New User",
        guild_id="guild-1",
    )


def test_empty_discord_profile_prompts_onboarding_once(tmp_path) -> None:
    source = _source()

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}):
        first_prompt = record_turn_and_build_prompt(
            source=source,
            text="안녕 미호",
            message_id="m1",
        )
        second_prompt = record_turn_and_build_prompt(
            source=source,
            text="다시 안녕",
            message_id="m2",
        )

    profile_path = tmp_path / "discord" / "users" / "user-1" / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["onboarding_prompted_at"]
    assert "Discord User Profile Onboarding" in str(first_prompt)
    assert "preferred_name" in str(first_prompt)
    assert "Discord User Profile Onboarding" not in str(second_prompt)


def test_existing_discord_profile_is_injected_for_that_user_only(tmp_path) -> None:
    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}):
        from gateway.discord_user_profile import upsert_discord_user_profile

        upsert_discord_user_profile(
            "user-1",
            preferred_name="민준",
            main_use_cases=["코딩 질문", "문서 정리"],
            response_style="짧고 명확하게",
        )
        prompt = record_turn_and_build_prompt(
            source=_source("user-1"),
            text="오늘 작업 정리해줘",
            message_id="m1",
        )
        other_prompt = record_turn_and_build_prompt(
            source=_source("user-2"),
            text="오늘 작업 정리해줘",
            message_id="m2",
        )

    assert "Relevant Discord User Profile" in str(prompt)
    assert "민준" in str(prompt)
    assert "짧고 명확하게" in str(prompt)
    assert "민준" not in str(other_prompt)


def test_discord_owner_profile_is_hidden_without_admin_gate(tmp_path) -> None:
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir(parents=True)
    (memories_dir / "USER.md").write_text(
        "비밀프로젝트는 owner 전용 맥락이다.",
        encoding="utf-8",
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}):
        prompt = record_turn_and_build_prompt(
            source=_source("user-2"),
            text="비밀프로젝트 정리해줘",
            message_id="m1",
        )

    assert "Relevant Owner Profile" not in str(prompt)
    assert "비밀프로젝트는 owner 전용 맥락이다" not in str(prompt)


def test_discord_owner_profile_is_injected_for_group_admin_only(tmp_path) -> None:
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir(parents=True)
    (memories_dir / "USER.md").write_text(
        "비밀프로젝트는 owner 전용 맥락이다.",
        encoding="utf-8",
    )
    (tmp_path / "config.yaml").write_text(
        "discord:\n  group_allow_admin_from:\n    - admin-user\n",
        encoding="utf-8",
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}):
        admin_prompt = record_turn_and_build_prompt(
            source=_source("admin-user"),
            text="비밀프로젝트 정리해줘",
            message_id="m1",
        )
        user_prompt = record_turn_and_build_prompt(
            source=_source("user-2"),
            text="비밀프로젝트 정리해줘",
            message_id="m2",
        )

    assert "Relevant Owner Profile" in str(admin_prompt)
    assert "비밀프로젝트는 owner 전용 맥락이다" in str(admin_prompt)
    assert "Relevant Owner Profile" not in str(user_prompt)
    assert "비밀프로젝트는 owner 전용 맥락이다" not in str(user_prompt)


def test_discord_profile_tool_saves_current_discord_user(tmp_path) -> None:
    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        tokens = set_session_vars(
            platform="discord",
            chat_id="channel-7",
            user_id="user-1",
            user_name="New User",
        )
        try:
            from tools.discord_profile_tool import discord_profile_tool

            result = json.loads(
                discord_profile_tool(
                    {
                        "action": "upsert",
                        "preferred_name": "민준",
                        "main_use_cases": ["코딩 질문"],
                        "response_style": "짧게",
                    }
                )
            )
        finally:
            clear_session_vars(tokens)

    assert result["success"] is True
    profile_path = tmp_path / "discord" / "users" / "user-1" / "profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile["preferred_name"] == "민준"
    assert profile["main_use_cases"] == ["코딩 질문"]


def test_discord_profile_tool_rejects_non_discord_context(tmp_path) -> None:
    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        tokens = set_session_vars(platform="telegram", chat_id="1", user_id="user-1")
        try:
            from tools.discord_profile_tool import discord_profile_tool

            result = json.loads(
                discord_profile_tool({"action": "upsert", "preferred_name": "민준"})
            )
        finally:
            clear_session_vars(tokens)

    assert result["success"] is False
    assert result["error"] == "discord_context_required"


def test_discord_profile_toolset_is_discord_only() -> None:
    from toolsets import resolve_toolset

    assert "discord_profile" in resolve_toolset("miho-discord")
    assert "discord_profile" not in resolve_toolset("miho-telegram")
    assert "discord_profile" not in resolve_toolset("miho-api-server")
