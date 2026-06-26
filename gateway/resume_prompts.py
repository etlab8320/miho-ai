"""Prompt builders for interrupted gateway turn recovery."""

from __future__ import annotations


def _interruption_reason_phrase(reason: str | None) -> str:
    if reason == "restart_timeout":
        return "a gateway restart"
    if reason == "shutdown_timeout":
        return "a gateway shutdown"
    return "a gateway interruption"


def build_resume_pending_message(user_message: str, *, reason: str | None) -> str:
    """Return the injected user message for a restart-resumed turn.

    Restart recovery must complete the interrupted user task, not surface a
    "shall I continue?" progress reply. Empty ``user_message`` means startup
    scheduled an internal auto-resume turn.
    """
    reason_phrase = _interruption_reason_phrase(reason)
    note = (
        "[System note: Your previous turn in this session was interrupted "
        f"by {reason_phrase}. The conversation history is intact. "
        "Continue the interrupted user request to a final user-visible answer. "
        "If the request asked for a file, PDF, image, or other media artifact, "
        "use the available tools or verified existing outputs to create, repair, "
        "or attach that artifact before replying. "
        "Do not ask whether to continue. "
        "Do not end with a progress update. "
        "Do not expose restart, recovery, retry, or internal verification wording. "
    )

    stripped = user_message.strip()
    if stripped:
        note += (
            "After the interrupted request is complete, address the new user "
            "message below.]"
        )
        return f"{note}\n\n{user_message}"

    note += (
        "This is an internal auto-resume turn with no new user text. Treat the "
        "most recent unfinished user request in the existing conversation as "
        "the active task and finish it now.]"
    )
    return note


__all__ = ["build_resume_pending_message"]
