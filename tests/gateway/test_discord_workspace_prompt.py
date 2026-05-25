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
        context_seed="seed " + ("z" * 3000),
        recent=recent,
        retrieved=retrieved,
        max_recent=3,
    )

    assert "retrieved-0" in prompt
    assert "retrieved-3" in prompt
    assert "retrieved-4" not in prompt
    assert "2 more retrieved item(s) omitted" in prompt
    assert "x" * 500 not in prompt
    assert "y" * 500 not in prompt
    assert "z" * 1300 not in prompt
    assert "without asking the user to do it manually" in prompt
    assert "do not restate unrelated retrieved context" in prompt
