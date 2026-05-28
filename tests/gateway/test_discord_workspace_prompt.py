from pathlib import Path
from types import SimpleNamespace

from gateway.discord_workspace_prompt import build_workspace_prompt


def test_workspace_prompt_applies_context_and_rag_budget():
    source = SimpleNamespace(chat_id="channel-1", parent_chat_id=None)
    retrieved = [
        {
            "role": "user",
            "user_name": f"u{idx}",
            "text": f"retrieved-{idx} " + ("x" * 900),
            "score": 0.9,
        }
        for idx in range(6)
    ]
    recent = [
        {"role": "user", "user_name": "max", "text": f"recent-{idx} " + ("y" * 900)}
        for idx in range(3)
    ]

    prompt = build_workspace_prompt(
        workspace_active_dir=Path("/tmp/workspace"),
        rag_dir=Path("/tmp/workspace/rag"),
        source=source,
        temporal_context=(
            "Turn time: calendar_date=2026-05-29, previous_calendar_date=2026-05-28, "
            "local_time=00:30, timezone=Asia/Seoul, after_midnight_window=true."
        ),
        context_seed="seed " + ("z" * 3000),
        owner_profile_context="### Relevant Owner Profile\n- [user] 날짜별 건강 기록",
        recent=recent,
        retrieved=retrieved,
        max_recent=3,
    )

    assert "Relevant Owner Profile" in prompt
    assert "날짜별 건강 기록" in prompt
    assert "retrieved-0" in prompt
    assert "retrieved-3" in prompt
    assert "retrieved-4" not in prompt
    assert "2 more retrieved item(s) omitted" in prompt
    assert "x" * 500 not in prompt
    assert "y" * 500 not in prompt
    assert "z" * 1300 not in prompt
    assert "without asking the user to do it manually" in prompt
    assert "do not restate unrelated retrieved context" in prompt
    assert "do not expose internal workflow" in prompt
    assert "previous_calendar_date=2026-05-28" in prompt
    assert "after_midnight_window=true" in prompt
    assert "life" + "_log_date" not in prompt
