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


def test_retry_executor_reruns_tool_until_reviewer_passes(monkeypatch) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    retry_result = {
        "success": True,
        "artifact_path": "/tmp/report.mhtml",
        "media_tag": "MEDIA:/tmp/report.mhtml",
        "reviewer": {
            "name": "attachment_delivery_review",
            "status": "pass",
            "checked": ["media_tag", "artifact_path"],
        },
    }

    def fake_dispatch(name: str, args: dict[str, object], **_kwargs: object) -> str:
        calls.append((name, args))
        return json.dumps(retry_result, ensure_ascii=False)

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)

    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        args={"artifact_path": "/tmp/report.mhtml"},
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
        tool_call_id="tool-call-1",
        governance_skip_ledger=True,
    )

    assert transformed is not None
    payload = json.loads(transformed)
    assert payload["reviewer"]["status"] == "pass"
    assert calls == [("media_delivery_contract", {"artifact_path": "/tmp/report.mhtml"})]


def test_retry_executor_keeps_block_payload_when_retry_fails(monkeypatch) -> None:
    def fake_dispatch(*_args: object, **_kwargs: object) -> str:
        return json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"})

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)

    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        args={"artifact_path": "/tmp/report.mhtml"},
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
        tool_call_id="tool-call-1",
        governance_skip_ledger=True,
    )

    assert transformed is not None
    payload = json.loads(transformed)
    assert payload["next_action"] == "retry_required"
    attempts = payload["auto_retry_executor"]["attempts"]
    assert attempts
    assert attempts[0]["status"] == "fail"


def test_retry_executor_fail_closes_when_retry_dispatch_raises(monkeypatch) -> None:
    def broken_dispatch(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("tool down")

    monkeypatch.setattr("tools.registry.registry.dispatch", broken_dispatch)

    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        args={"artifact_path": "/tmp/report.mhtml"},
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
        tool_call_id="tool-call-1",
        governance_skip_ledger=True,
    )

    assert transformed is not None
    payload = json.loads(transformed)
    assert payload["next_action"] == "retry_required"
    attempts = payload["auto_retry_executor"]["attempts"]
    assert attempts[0]["status"] == "fail"
    assert attempts[0]["reason"] == "retry_dispatch_error:RuntimeError"
