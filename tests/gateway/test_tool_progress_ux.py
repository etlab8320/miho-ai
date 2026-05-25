from gateway.tool_progress_ux import (
    media_delivery_failure_message,
    render_clean_tool_progress,
    should_emit_clean_progress,
)


def test_clean_progress_hides_tool_names():
    message = render_clean_tool_progress("terminal", "python render_card.py")

    assert "terminal" not in message
    assert "python" not in message
    assert message == "작업을 진행하고 검증하는 중..."


def test_clean_progress_groups_common_coding_tools_to_reduce_chat_noise():
    messages = {
        render_clean_tool_progress("read_file"),
        render_clean_tool_progress("terminal", "pytest"),
        render_clean_tool_progress("execute_code", "inspect data"),
    }

    assert messages == {"작업을 진행하고 검증하는 중..."}


def test_clean_progress_uses_visual_copy_for_images():
    message = render_clean_tool_progress("execute_code", "render html to png")

    assert message == "결과물을 빚고 검수하는 중..."


def test_clean_progress_emits_common_status_once_per_run():
    seen: set[str] = set()
    common = "작업을 진행하고 검증하는 중..."

    assert should_emit_clean_progress(common, seen) is True
    assert should_emit_clean_progress(common, seen) is False
    assert should_emit_clean_progress("작업을 진행하고 검증하는 중...", seen) is False
    assert should_emit_clean_progress("작업 흐름을 정리하는 중...", seen) is False


def test_clean_progress_allows_artifact_status_after_common_status():
    seen = {"작업을 진행하고 검증하는 중..."}

    assert should_emit_clean_progress("결과물을 빚고 검수하는 중...", seen) is True


def test_media_failure_message_is_plain_korean():
    message = media_delivery_failure_message("discord")

    assert "첨부 전송" in message
    assert "HTTP" not in message
    assert "stack" not in message.lower()
