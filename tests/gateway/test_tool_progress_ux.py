from gateway.tool_progress_ux import (
    media_delivery_failure_message,
    render_clean_tool_progress,
)


def test_clean_progress_hides_tool_names():
    message = render_clean_tool_progress("terminal", "python render_card.py")

    assert "terminal" not in message
    assert "python" not in message
    assert message == "안쪽에서 계산하고 검증하는 중..."


def test_clean_progress_uses_visual_copy_for_images():
    message = render_clean_tool_progress("execute_code", "render html to png")

    assert message == "결과물을 빚고 검수하는 중..."


def test_media_failure_message_is_plain_korean():
    message = media_delivery_failure_message("discord")

    assert "첨부 전송" in message
    assert "HTTP" not in message
    assert "stack" not in message.lower()
