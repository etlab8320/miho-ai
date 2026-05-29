import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import gateway.discord_workspace_vectors as _vectors
from gateway.config import Platform
from gateway.discord_workspace import (
    archive_workspace_for_channel,
    archive_workspace_for_thread,
    ensure_workspace_for_channel,
    ensure_workspace_for_thread,
    record_assistant_turn,
    record_turn_and_build_prompt,
)
from gateway.session import SessionSource

# Topic anchors for the semantic-retrieval test double below. A real embedding
# places "로그인 방식" near "로그인 OAuth" and far from "점심 김밥"; this fixture
# reproduces that proximity deterministically by projecting each text onto a few
# topic axes. It is a TEST DOUBLE for an embedding provider, not production
# routing logic — retrieval tests must not depend on the hash fallback, which
# carries no meaning and is now correctly ignored by retrieve_rag_context.
_TOPIC_AXES = (
    ("로그인", "oauth", "인증", "login", "계정", "discord", "처리"),
    ("점심", "김밥", "식사", "메뉴"),
    ("결제", "반영", "확인", "규칙", "안전", "실행", "버튼"),
)


def _bow_embed(text: str, input_type: str = "document"):
    """Deterministic topic embedding standing in for a real provider."""
    tokens = set(_vectors._tokens(text))
    vec = [float(sum(1 for w in axis if w in tokens)) for axis in _TOPIC_AXES]
    vec.append(0.1)  # small bias so unrelated text is never a zero vector
    return vec, "voyage-4-large"


def test_record_turn_creates_channel_thread_rag_workspace(tmp_path):
    source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="thread-9",
        chat_name="Academy / Design Sprint",
        chat_type="thread",
        user_id="user-1",
        user_name="ET",
        thread_id="thread-9",
        guild_id="guild-1",
        parent_chat_id="channel-7",
        message_id="msg-1",
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        prompt = record_turn_and_build_prompt(
            source=source,
            text="이번 스레드는 Peak/Paka 로그인 연동 설계야.",
            message_id="msg-1",
        )

    channel_root = tmp_path / "discord" / "guilds" / "guild-1" / "channels"
    channel_dirs = list(channel_root.iterdir())
    assert len(channel_dirs) == 1
    thread_dirs = list((channel_dirs[0] / "threads").iterdir())
    assert len(thread_dirs) == 1

    rag_dir = thread_dirs[0] / "rag"
    assert (rag_dir / "messages.jsonl").exists()
    assert (rag_dir / "index.json").exists()
    index = json.loads((rag_dir / "index.json").read_text(encoding="utf-8"))
    assert index["kind"] == "miho-discord-thread-rag"
    assert index["message_count"] == 1
    parent_index = json.loads(
        (channel_dirs[0] / "rag" / "index.json").read_text(encoding="utf-8")
    )
    assert parent_index["kind"] == "miho-discord-channel-rag"
    assert parent_index["message_count"] == 1
    assert "Miho Discord Workspace RAG" in prompt
    assert "Peak/Paka 로그인" in prompt


def test_record_turn_tracks_current_and_previous_dates_after_midnight(tmp_path):
    source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="thread-log",
        chat_name="log",
        chat_type="thread",
        user_id="u1",
        user_name="Max",
        thread_id="thread-log",
        guild_id="guild-1",
        parent_chat_id="channel-7",
        message_id="m1",
    )
    timestamp = datetime(2026, 5, 29, 0, 40, tzinfo=ZoneInfo("Asia/Seoul"))

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        prompt = record_turn_and_build_prompt(
            source=source,
            text="오늘 먹은 거 전체 칼로리 정리해줘",
            message_id="m1",
            timestamp=timestamp,
        )

    messages_path = next(
        (tmp_path / "discord" / "guilds" / "guild-1" / "channels").glob(
            "*/threads/*/rag/messages.jsonl"
        )
    )
    record = json.loads(messages_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["date"] == "2026-05-29"
    assert record["previous_calendar_date"] == "2026-05-28"
    assert record["after_midnight_window"] is True
    assert "previous_calendar_date=2026-05-28" in prompt


def test_record_turn_appends_recent_context(tmp_path):
    source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="channel-7",
        chat_name="general",
        chat_type="group",
        user_id="u1",
        user_name="Max",
        guild_id="guild-1",
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        record_turn_and_build_prompt(source=source, text="첫 번째 결정", message_id="m1")
        prompt = record_turn_and_build_prompt(
            source=source,
            text="두 번째 결정",
            message_id="m2",
        )

    assert "첫 번째 결정" in prompt
    assert "두 번째 결정" in prompt
    index_path = next(
        (tmp_path / "discord" / "guilds" / "guild-1" / "channels").glob(
            "*/rag/index.json"
        )
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    assert index["kind"] == "miho-discord-channel-rag"
    assert index["message_count"] == 2
    assert index["vector_count"] == 2
    assert (index_path.parent / "vectors.jsonl").exists()


def test_record_turn_retrieves_relevant_vector_memory(tmp_path):
    source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="channel-7",
        chat_name="general",
        chat_type="group",
        user_id="u1",
        user_name="Max",
        guild_id="guild-1",
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}), patch(
        "gateway.discord_workspace_vectors.embed_text", _bow_embed
    ):
        record_turn_and_build_prompt(
            source=source,
            text="Peak Paka 로그인은 Discord OAuth로 처리한다.",
            message_id="m1",
        )
        record_turn_and_build_prompt(
            source=source,
            text="오늘 점심은 김밥으로 정했다.",
            message_id="m2",
        )
        prompt = record_turn_and_build_prompt(
            source=source,
            text="로그인 방식 다시 정리해줘.",
            message_id="m3",
        )

    assert "Retrieved Relevant Memory" in prompt
    assert "Discord OAuth" in prompt
    retrieved_section = prompt.split("### Retrieved Relevant Memory", 1)[1]
    retrieved_section = retrieved_section.split("### Recent Thread Messages", 1)[0]
    assert "김밥" not in retrieved_section


def test_record_turn_stores_kst_date_in_messages_and_vectors(tmp_path):
    source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="channel-7",
        chat_name="log",
        chat_type="group",
        user_id="u1",
        user_name="Max",
        guild_id="guild-1",
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}):
        prompt = record_turn_and_build_prompt(
            source=source,
            text="오늘은 바나나 1개랑 324칼로리 도시락을 먹었어.",
            message_id="m-log",
            timestamp=datetime(2026, 5, 28, 23, 30, tzinfo=timezone.utc),
        )

    rag_dir = next((tmp_path / "discord" / "guilds" / "guild-1" / "channels").glob("*/rag"))
    message = json.loads((rag_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    vector = json.loads((rag_dir / "vectors.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert message["date"] == "2026-05-29"
    assert message["timezone"] == "Asia/Seoul"
    assert vector["date"] == "2026-05-29"
    assert "[2026-05-29 user:Max]" in str(prompt)
    assert "calendar_date=2026-05-29" in str(prompt)


def test_record_turn_injects_relevant_owner_profile_context(tmp_path):
    source = SessionSource(
        platform=Platform.DISCORD,
        chat_id="channel-7",
        chat_name="log",
        chat_type="group",
        user_id="u1",
        user_name="Max",
        guild_id="guild-1",
    )
    memories_dir = tmp_path / "memories"
    memories_dir.mkdir(parents=True)
    (memories_dir / "USER.md").write_text(
        "- 기록: Max는 칼로리와 체중을 날짜별로 분리해서 정리해야 한다.\n"
        "§\n"
        "- 개발: ET는 커밋 전 스모크 테스트를 선호한다.\n",
        encoding="utf-8",
    )
    (tmp_path / "config.yaml").write_text(
        "discord:\n  group_allow_admin_from:\n    - u1\n",
        encoding="utf-8",
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}):
        prompt = record_turn_and_build_prompt(
            source=source,
            text="오늘 먹은 전체 칼로리를 날짜 기준으로 다시 계산해줘.",
            message_id="m-log-profile",
        )

    assert "Relevant Owner Profile" in str(prompt)
    assert "칼로리와 체중을 날짜별로" in str(prompt)
    assert "커밋 전 스모크" not in str(prompt)


def test_assistant_turn_is_indexed_in_thread_and_parent(tmp_path):
    source = SessionSource(
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

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}):
        record_turn_and_build_prompt(source=source, text="결정 후보를 봐줘.", message_id="m1")
        record_assistant_turn(source=source, text="최종 결정은 Discord OAuth가 안전하다.")

    channel_dir = next((tmp_path / "discord" / "guilds" / "guild-1" / "channels").iterdir())
    thread_dir = next((channel_dir / "threads").iterdir())
    thread_lines = (thread_dir / "rag" / "messages.jsonl").read_text(encoding="utf-8").splitlines()
    parent_lines = (channel_dir / "rag" / "messages.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(thread_lines[-1])["role"] == "assistant"
    assert "Discord OAuth" in json.loads(parent_lines[-1])["text"]


def test_channel_and_thread_creation_events_can_preseed_workspaces(tmp_path):
    guild = SimpleNamespace(id="guild-1")
    channel = SimpleNamespace(id="channel-7", name="miho-room", topic="운영 채널", guild=guild)
    thread = SimpleNamespace(
        id="thread-9",
        name="login-plan",
        parent=channel,
        guild=guild,
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        channel_ws = ensure_workspace_for_channel(channel)
        thread_ws = ensure_workspace_for_thread(thread)

    assert channel_ws is not None
    assert thread_ws is not None
    assert (channel_ws.channel_dir / "channel.json").exists()
    assert (thread_ws.active_dir / "thread.json").exists()
    assert (thread_ws.rag_dir / "index.json").exists()


def test_thread_message_reuses_preseeded_channel_dir_by_id(tmp_path):
    guild = SimpleNamespace(id="guild-1")
    channel = SimpleNamespace(id="channel-7", name="miho-room", topic="", guild=guild)

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        preseed = ensure_workspace_for_channel(channel)
        source = SessionSource(
            platform=Platform.DISCORD,
            chat_id="thread-9",
            chat_name="Login Thread",
            chat_type="thread",
            user_id="u1",
            user_name="ET",
            thread_id="thread-9",
            guild_id="guild-1",
            parent_chat_id="channel-7",
        )
        record_turn_and_build_prompt(source=source, text="스레드 시작", message_id="m1")

    channel_root = tmp_path / "discord" / "guilds" / "guild-1" / "channels"
    channel_dirs = list(channel_root.iterdir())
    assert channel_dirs == [preseed.channel_dir]
    assert list((preseed.channel_dir / "threads").iterdir())


def test_thread_prompt_does_not_include_parent_or_sibling_messages(tmp_path):
    first = SessionSource(
        platform=Platform.DISCORD,
        chat_id="thread-1",
        chat_name="First Thread",
        chat_type="thread",
        user_id="u1",
        user_name="ET",
        thread_id="thread-1",
        guild_id="guild-1",
        parent_chat_id="channel-7",
    )
    sibling = SessionSource(
        platform=Platform.DISCORD,
        chat_id="thread-2",
        chat_name="Sibling Thread",
        chat_type="thread",
        user_id="u2",
        user_name="Max",
        thread_id="thread-2",
        guild_id="guild-1",
        parent_chat_id="channel-7",
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        record_turn_and_build_prompt(
            source=sibling,
            text="형제 스레드 비밀",
            message_id="m-sibling",
        )
        prompt = record_turn_and_build_prompt(
            source=first,
            text="내 스레드 내용",
            message_id="m-first",
        )

    assert "내 스레드 내용" in prompt
    assert "형제 스레드 비밀" not in prompt


def test_thread_prompt_can_retrieve_parent_channel_common_memory(tmp_path):
    parent = SessionSource(
        platform=Platform.DISCORD,
        chat_id="channel-7",
        chat_name="parent",
        chat_type="group",
        user_id="u1",
        user_name="ET",
        guild_id="guild-1",
    )
    thread = SessionSource(
        platform=Platform.DISCORD,
        chat_id="thread-1",
        chat_name="First Thread",
        chat_type="thread",
        user_id="u1",
        user_name="ET",
        thread_id="thread-1",
        guild_id="guild-1",
        parent_chat_id="channel-7",
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}), patch(
        "gateway.discord_workspace_vectors.embed_text", _bow_embed
    ):
        record_turn_and_build_prompt(
            source=parent,
            text="학원 업무 공통 규칙: 결제 반영은 확인 버튼 없이는 실행하지 않는다.",
            message_id="m-parent",
        )
        prompt = record_turn_and_build_prompt(
            source=thread,
            text="결제 반영 안전 규칙 다시 확인해줘.",
            message_id="m-thread",
        )

    assert "Retrieved Relevant Memory" in prompt
    assert "확인 버튼 없이는 실행하지 않는다" in prompt


def test_parent_channel_rag_receives_child_thread_events(tmp_path):
    thread = SessionSource(
        platform=Platform.DISCORD,
        chat_id="thread-1",
        chat_name="First Thread",
        chat_type="thread",
        user_id="u1",
        user_name="ET",
        thread_id="thread-1",
        guild_id="guild-1",
        parent_chat_id="channel-7",
    )
    parent = SessionSource(
        platform=Platform.DISCORD,
        chat_id="channel-7",
        chat_name="parent",
        chat_type="group",
        user_id="u1",
        user_name="ET",
        guild_id="guild-1",
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        record_turn_and_build_prompt(
            source=thread,
            text="자식 스레드 결정",
            message_id="m-thread",
        )
        prompt = record_turn_and_build_prompt(
            source=parent,
            text="부모 채널 질문",
            message_id="m-parent",
        )

    assert "자식 스레드 결정" in prompt
    assert "부모 채널 질문" in prompt
    assert "Thread ID" not in prompt


def test_deleted_thread_workspace_is_archived(tmp_path):
    guild = SimpleNamespace(id="guild-1")
    channel = SimpleNamespace(id="channel-7", name="miho-room", topic="", guild=guild)
    thread = SimpleNamespace(
        id="thread-9",
        name="login-plan",
        parent=channel,
        guild=guild,
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        workspace = ensure_workspace_for_thread(thread)
        archived = archive_workspace_for_thread(thread)

    assert workspace is not None
    assert archived is not None
    assert not workspace.active_dir.exists()
    assert archived.exists()
    assert (archived / "rag" / "index.json").exists()
    archive_meta = json.loads((archived / "archive.json").read_text(encoding="utf-8"))
    assert archive_meta["reason"] == "discord_thread_deleted"
    assert archive_meta["thread_id"] == "thread-9"


def test_deleted_channel_workspace_archives_child_threads(tmp_path):
    guild = SimpleNamespace(id="guild-1")
    channel = SimpleNamespace(id="channel-7", name="miho-room", topic="", guild=guild)
    thread = SimpleNamespace(
        id="thread-9",
        name="login-plan",
        parent=channel,
        guild=guild,
    )

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        channel_ws = ensure_workspace_for_channel(channel)
        ensure_workspace_for_thread(thread)
        archived = archive_workspace_for_channel(channel)

    assert channel_ws is not None
    assert archived is not None
    assert not channel_ws.channel_dir.exists()
    assert (archived / "rag" / "index.json").exists()
    assert (archived / "threads").exists()
    archive_meta = json.loads((archived / "archive.json").read_text(encoding="utf-8"))
    assert archive_meta["reason"] == "discord_channel_deleted"
    assert archive_meta["channel_id"] == "channel-7"
