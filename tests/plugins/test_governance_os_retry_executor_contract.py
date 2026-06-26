"""Retry executor contract coverage for governed tool-result failures."""

from __future__ import annotations

import json

from plugins.governance_os.result_transform import governance_transform_tool_result


def test_retry_required_payload_contains_agentic_executor_contract() -> None:
    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        args={"artifact_path": "/tmp/report.mhtml"},
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
        tool_call_id="tool-call-1",
    )

    assert transformed is not None
    payload = json.loads(transformed)
    executor = payload["auto_retry_executor"]
    assert executor["status"] == "required"
    assert executor["mode"] == "agentic_tool_loop"
    assert executor["tool_call_id"] == "tool-call-1"
    assert executor["retry_tools"] == ["media_delivery_contract"]
    assert executor["retry_args"] == [{"artifact_path": "/tmp/report.mhtml"}]
    assert "후검증" not in executor["user_visible_summary"]
    assert "retry_tools" not in executor["user_visible_summary"]
