from gateway.tool_progress_ux import (
    media_delivery_failure_message,
    render_clean_finish_progress,
    render_clean_start_progress,
    render_clean_tool_progress,
    should_emit_clean_progress,
)


def test_clean_start_progress_is_immediate_plain_korean():
    assert render_clean_start_progress() == "작업 카드 | 요청 확인"


def test_clean_progress_hides_tool_names():
    message = render_clean_tool_progress("terminal", "python render_card.py")

    assert "terminal" not in message
    assert "python" not in message
    assert message == "작업 카드 | 작업 실행"


def test_clean_progress_groups_tools_into_user_visible_stages():
    messages = {
        render_clean_tool_progress("read_file"),
        render_clean_tool_progress("terminal", "pytest"),
        render_clean_tool_progress("execute_code", "inspect data"),
    }

    assert messages == {
        "작업 카드 | 맥락 확인",
        "작업 카드 | 검증 중",
        "작업 카드 | 작업 실행",
    }


def test_clean_progress_uses_visual_copy_for_images():
    message = render_clean_tool_progress("execute_code", "render html to png")

    assert message == "작업 카드 | 결과물 확인"


def test_clean_progress_emits_common_status_once_per_run():
    seen: set[str] = set()
    common = "작업 카드 | 맥락 확인"

    assert should_emit_clean_progress(common, seen) is True
    assert should_emit_clean_progress(common, seen) is False
    assert should_emit_clean_progress("작업 카드 | 맥락 확인", seen) is False
    assert should_emit_clean_progress("작업 카드 | 자료 확인", seen) is True
    assert should_emit_clean_progress("작업 카드 | 검증 중", seen) is True
    assert should_emit_clean_progress("작업 카드 | 작업 흐름 정리", seen) is False


def test_clean_progress_allows_artifact_status_after_stage_limit():
    seen = {
        "작업 카드 | 맥락 확인",
        "작업 카드 | 자료 확인",
        "작업 카드 | 검증 중",
    }

    assert should_emit_clean_progress("작업 카드 | 결과물 확인", seen) is True


def test_clean_progress_allows_finish_status_after_stage_limit():
    seen = {
        "작업 카드 | 맥락 확인",
        "작업 카드 | 자료 확인",
        "작업 카드 | 검증 중",
    }

    assert should_emit_clean_progress("작업 카드 | 완료", seen) is True
    assert render_clean_finish_progress({"failed": True}) == "작업 카드 | 확인 필요"
    assert render_clean_finish_progress({"interrupted": True}) == "작업 카드 | 중단됨"


def test_media_failure_message_is_plain_korean():
    message = media_delivery_failure_message("discord")

    assert "첨부 전송" in message
    assert "HTTP" not in message
    assert "stack" not in message.lower()
