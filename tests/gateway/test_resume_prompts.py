"""Regression tests for gateway restart recovery prompts."""

from gateway.resume_prompts import build_resume_pending_message


def test_empty_auto_resume_continues_interrupted_request():
    message = build_resume_pending_message(
        "",
        reason="restart_interrupted",
    )

    assert "internal auto-resume turn" in message
    assert "most recent unfinished user request" in message
    assert "Continue the interrupted user request" in message
    assert "final user-visible answer" in message
    assert "Do not ask whether to continue" in message
    assert "Do not end with a progress update" in message
    assert "summarize what was accomplished" not in message
    assert "address the user's new message below" not in message


def test_real_user_message_is_preserved_after_resume_note():
    message = build_resume_pending_message(
        "이어서 PDF 다시 줘",
        reason="restart_timeout",
    )

    assert "gateway restart" in message
    assert "After the interrupted request is complete" in message
    assert message.endswith("이어서 PDF 다시 줘")


def test_shutdown_reason_is_explicit():
    message = build_resume_pending_message("ping", reason="shutdown_timeout")

    assert "gateway shutdown" in message
