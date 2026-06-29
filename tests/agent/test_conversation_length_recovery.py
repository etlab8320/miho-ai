from types import SimpleNamespace

from agent.conversation_length_recovery import handle_finish_reason_and_length


class _Transport:
    def normalize_response(self, response, **kwargs):
        return SimpleNamespace(
            content=getattr(response, "content", None),
            tool_calls=getattr(response, "tool_calls", None),
            finish_reason=getattr(response, "finish_reason", "stop"),
        )


class _Agent:
    api_mode = "codex_responses"
    log_prefix = ""

    def __init__(self):
        self.persisted = None
        self.cleaned = []

    def _get_transport(self):
        return _Transport()

    def _vprint(self, *args, **kwargs):
        pass

    def _has_content_after_think_block(self, content):
        return bool(str(content or "").strip())

    def _strip_think_blocks(self, content):
        return str(content or "")

    def _build_assistant_message(self, assistant_message, finish_reason):
        return {
            "role": "assistant",
            "content": assistant_message.content,
            "finish_reason": finish_reason,
        }

    def _cleanup_task_resources(self, task_id):
        self.cleaned.append(task_id)

    def _persist_session(self, messages, conversation_history):
        self.persisted = list(messages)

    def _get_messages_up_to_last_assistant(self, messages):
        for idx in range(len(messages) - 1, -1, -1):
            if messages[idx].get("role") == "assistant":
                return messages[: idx + 1]
        return []

    def _should_treat_stop_as_truncated(self, finish_reason, result, messages):
        return False


def _codex_truncated_response(content=None, tool_calls=None):
    return SimpleNamespace(
        status="incomplete",
        incomplete_details={"reason": "max_output_tokens"},
        content=content,
        tool_calls=tool_calls,
    )


def test_codex_length_text_gets_continuation_instead_of_rollback():
    agent = _Agent()
    messages = [{"role": "user", "content": "작업해줘"}]

    result = handle_finish_reason_and_length(
        agent=agent,
        response=_codex_truncated_response(content="여기까지 작업 결과"),
        messages=messages,
        conversation_history=None,
        effective_task_id="task-1",
        api_call_count=1,
        length_continue_retries=0,
        truncated_tool_call_retries=0,
        truncated_response_parts=[],
    )

    assert result.action == "break_retry"
    assert result.restart_with_length_continuation is True
    assert result.truncated_response_parts == ["여기까지 작업 결과"]
    assert messages[-1]["role"] == "user"
    assert "Continue exactly where you left off" in messages[-1]["content"]


def test_truncation_exhaustion_returns_user_visible_partial():
    agent = _Agent()
    messages = [{"role": "user", "content": "작업해줘"}]

    result = handle_finish_reason_and_length(
        agent=agent,
        response=_codex_truncated_response(content="마지막 부분"),
        messages=messages,
        conversation_history=None,
        effective_task_id="task-2",
        api_call_count=3,
        length_continue_retries=2,
        truncated_tool_call_retries=0,
        truncated_response_parts=["앞부분 "],
    )

    assert result.action == "return"
    assert result.return_value is not None
    assert result.return_value["partial"] is True
    assert result.return_value["final_response"].startswith("앞부분 마지막 부분")
    assert "길이 제한" in result.return_value["final_response"]


def test_unknown_truncation_returns_checkpoint_instead_of_silent_none():
    agent = _Agent()
    agent.api_mode = "unknown_provider"
    messages = [
        {"role": "user", "content": "처음"},
        {"role": "assistant", "content": "중간 완료"},
        {"role": "user", "content": "계속"},
    ]
    response = SimpleNamespace(finish_reason="length", content=None, tool_calls=None)

    result = handle_finish_reason_and_length(
        agent=agent,
        response=response,
        messages=messages,
        conversation_history=None,
        effective_task_id="task-3",
        api_call_count=4,
        length_continue_retries=0,
        truncated_tool_call_retries=0,
        truncated_response_parts=[],
    )

    assert result.action == "return"
    assert result.return_value is not None
    assert result.return_value["final_response"]
    assert "출력 길이 제한" in result.return_value["final_response"]
    assert result.return_value["messages"] == messages[:2]
