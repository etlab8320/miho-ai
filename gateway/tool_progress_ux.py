"""User-facing gateway progress copy for Miho chat platforms."""

from __future__ import annotations

from typing import Any


_RESEARCH_TOOLS = {
    "web_search",
    "web_fetch",
    "browser_navigate",
    "browser_search",
    "browser_open",
}
_BUILD_TOOLS = {
    "execute_code",
    "terminal",
    "python",
    "shell",
}
_VISUAL_TOOLS = {
    "vision_analyze",
    "image_generation",
    "image_gen",
    "browser_screenshot",
}
_MEMORY_TOOLS = {
    "memory",
    "skill_view",
    "read_file",
    "search_files",
    "list_files",
}

_ARTIFACT_STAGE = "작업 카드 | 결과물 확인"
_FINISH_STAGES = {
    "completed": "작업 카드 | 완료",
    "failed": "작업 카드 | 확인 필요",
    "interrupted": "작업 카드 | 중단됨",
}


def render_clean_start_progress() -> str:
    """Return the first visible sign that Miho accepted the request."""
    return "작업 카드 | 요청 확인"


def should_emit_clean_progress(
    message: str,
    seen_messages: set[str],
    *,
    max_messages: int = 3,
) -> bool:
    """Return True when a clean progress message should be shown for this run."""
    if not message or message in seen_messages:
        return False
    if len(seen_messages) >= max_messages and message not in {_ARTIFACT_STAGE, *_FINISH_STAGES.values()}:
        return False
    seen_messages.add(message)
    return True


def render_clean_tool_progress(tool_name: str | None, preview: str | None = None) -> str:
    """Return a concise Korean status line without exposing internal tool names."""
    name = str(tool_name or "").strip()
    preview_text = str(preview or "").strip()
    preview_lower = preview_text.lower()

    if name in _BUILD_TOOLS:
        if any(word in preview_lower for word in ("html", "png", "image", "screenshot")):
            return _ARTIFACT_STAGE
        if any(word in preview_lower for word in ("pytest", "ruff", "test", "check", "lint")):
            return "작업 카드 | 검증 중"
        return "작업 카드 | 작업 실행"
    if name in _RESEARCH_TOOLS:
        return "작업 카드 | 자료 확인"
    if name in _MEMORY_TOOLS:
        return "작업 카드 | 맥락 확인"
    if name in _VISUAL_TOOLS:
        return _ARTIFACT_STAGE
    return "작업 카드 | 작업 중"


def render_clean_finish_progress(result: dict[str, Any] | None = None) -> str:
    """Return the last clean progress stage for an agent run."""
    payload = result or {}
    if payload.get("interrupted"):
        return _FINISH_STAGES["interrupted"]
    if payload.get("failed") or payload.get("error"):
        return _FINISH_STAGES["failed"]
    return _FINISH_STAGES["completed"]


def media_delivery_failure_message(platform: Any = None) -> str:
    """Friendly message when generated media cannot be attached safely."""
    return (
        "이미지는 만들었는데 첨부 전송에서 막혔어. "
        "내부 오류 문구는 숨겨둘게. 다시 만들거나 다른 경로로 보내볼게."
    )
