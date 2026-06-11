"""Provenance coverage for Discord workspace RAG."""

from __future__ import annotations

import json
from unittest.mock import patch

from gateway.config import Platform
from gateway.discord_workspace import record_assistant_turn, record_turn_and_build_prompt
from gateway.session import SessionSource


def _source() -> SessionSource:
    return SessionSource(
        platform=Platform.DISCORD,
        chat_id="thread-9",
        chat_name="Academy / Design Sprint",
        chat_type="thread",
        user_id="user-1",
        user_name="ET",
        thread_id="thread-9",
        guild_id="guild-1",
        parent_chat_id="channel-7",
    )


def _embed(text: str, input_type: str | None = None):
    return [1.0, 0.0], "test-embedding"


def test_workspace_rag_marks_user_and_assistant_provenance(tmp_path) -> None:
    source = _source()

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}), patch(
        "gateway.discord_workspace_vectors.embed_text",
        _embed,
    ):
        record_turn_and_build_prompt(source=source, text="결정 후보를 봐줘.", message_id="m1")
        record_assistant_turn(source=source, text="최종 결정은 Discord OAuth가 안전하다.")
        prompt = record_turn_and_build_prompt(source=source, text="Discord OAuth 결정 다시 확인", message_id="m2")

    channel_dir = next((tmp_path / "discord" / "guilds" / "guild-1" / "channels").iterdir())
    thread_dir = next((channel_dir / "threads").iterdir())
    messages = [
        json.loads(line)
        for line in (thread_dir / "rag" / "messages.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    vectors = [
        json.loads(line)
        for line in (thread_dir / "rag" / "vectors.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert messages[0]["source_kind"] == "user_message"
    assert messages[1]["source_kind"] == "assistant_inference"
    assert vectors[1]["source_kind"] == "assistant_inference"
    assert "assistant_inference" in str(prompt)
