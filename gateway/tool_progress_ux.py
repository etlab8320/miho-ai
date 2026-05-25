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


def render_clean_start_progress() -> str:
    """Return the first visible sign that Miho accepted the request."""
    return "요청을 살펴보는 중..."


def should_emit_clean_progress(
    message: str,
    seen_messages: set[str],
    *,
    max_messages: int = 3,
) -> bool:
    """Return True when a clean progress message should be shown for this run."""
    if not message or message in seen_messages:
        return False
    if len(seen_messages) >= max_messages and message != "결과물을 빚고 검수하는 중...":
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
            return "결과물을 빚고 검수하는 중..."
        if any(word in preview_lower for word in ("pytest", "ruff", "test", "check", "lint")):
            return "테스트와 검증을 실행하는 중..."
        return "명령을 실행하고 결과를 확인하는 중..."
    if name in _RESEARCH_TOOLS:
        return "필요한 자료를 확인하는 중..."
    if name in _MEMORY_TOOLS:
        return "관련 맥락을 확인하는 중..."
    if name in _VISUAL_TOOLS:
        return "결과물을 빚고 검수하는 중..."
    return "작업을 진행하고 검증하는 중..."


def media_delivery_failure_message(platform: Any = None) -> str:
    """Friendly message when generated media cannot be attached safely."""
    return (
        "이미지는 만들었는데 첨부 전송에서 막혔어. "
        "내부 오류 문구는 숨겨둘게. 다시 만들거나 다른 경로로 보내볼게."
    )
