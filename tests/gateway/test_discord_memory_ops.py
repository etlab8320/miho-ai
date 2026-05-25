import json
import sqlite3
from unittest.mock import patch

from gateway.config import Platform
from gateway.discord_memory_ops import run_memory_command
from gateway.discord_workspace import record_turn_and_build_prompt
from gateway.session import SessionSource


def _source() -> SessionSource:
    return SessionSource(
        platform=Platform.DISCORD,
        chat_id="thread-9",
        chat_name="Coding Thread",
        chat_type="thread",
        user_id="user-1",
        user_name="ET",
        thread_id="thread-9",
        guild_id="guild-1",
        parent_chat_id="channel-7",
    )


def test_memory_status_reports_current_workspace(tmp_path):
    source = _source()

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}):
        record_turn_and_build_prompt(source=source, text="Miho 기억 테스트", message_id="m1")
        output = run_memory_command(source, "status")

    assert "Miho Discord memory" in output
    assert "Scope: thread" in output
    assert "Messages: 1" in output
    assert "Vectors: 1" in output


def test_memory_search_returns_relevant_memory(tmp_path):
    source = _source()

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}):
        record_turn_and_build_prompt(source=source, text="세법 검토는 국세청 자료를 우선한다.", message_id="m1")
        record_turn_and_build_prompt(source=source, text="점심은 김밥으로 정했다.", message_id="m2")
        output = run_memory_command(source, "search 세법 국세청")

    assert "Miho memory search" in output
    assert "국세청" in output


def test_memory_rebuild_recreates_vectors(tmp_path):
    source = _source()

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path), "OPENAI_API_KEY": ""}):
        record_turn_and_build_prompt(source=source, text="KBO 프리뷰는 선발투수부터 본다.", message_id="m1")
        workspace_root = tmp_path / "discord" / "guilds" / "guild-1" / "channels"
        thread_dir = next(next(workspace_root.iterdir()).joinpath("threads").iterdir())
        vector_path = thread_dir / "rag" / "vectors.jsonl"
        vector_path.write_text("", encoding="utf-8")
        output = run_memory_command(source, "rebuild")

    assert "기억 재색인 완료: 1개 메시지" in output
    lines = vector_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["text"] == "KBO 프리뷰는 선발투수부터 본다."


def test_memory_promote_writes_owner_profile_event(tmp_path):
    source = _source()

    with patch.dict("os.environ", {"MIHO_HOME": str(tmp_path)}):
        output = run_memory_command(
            source,
            "promote 미호는 스레드 RAG와 장기기억 Vault를 분리해서 관리한다.",
        )

    assert "장기기억으로 승격" in output
    db_path = tmp_path / "memories" / "owner_profile" / "timeline.db"
    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT category, content, source FROM profile_events"
        ).fetchone()
    assert row[0] == "discord_memory"
    assert "장기기억 Vault" in row[1]
    assert "thread/thread-9" in row[2]
