"""Governance OS subagent routing hook smoke tests."""

from __future__ import annotations

import json

import pytest

from plugins.governance_os.dispatcher import governance_pre_gateway_dispatch
from plugins.governance_os.result_transform import governance_transform_tool_result


class _Source:
    user_id = "owner"


class _Event:
    source = _Source()

    def __init__(self, text: str) -> None:
        self.text = text
        self.message_id = "smoke-msg"


class _Gateway:
    def _is_user_authorized(self, source: object) -> bool:
        return bool(source)


@pytest.mark.asyncio
async def test_subagent_routing_smoke_keeps_user_error_korean_and_plain(
    monkeypatch,
) -> None:
    import agent.auxiliary_client as auxiliary_client

    async def fake_dispatcher(**_: object) -> dict[str, object]:
        return json.dumps(
            {
                "playbook_key": "discord_attachment_delivery",
                "confidence": 0.9,
                "reason": "attachment path",
            },
            ensure_ascii=False,
        )

    def broken_reviewer(**_: object) -> str:
        raise RuntimeError("provider offline")

    monkeypatch.setattr(auxiliary_client, "async_call_llm", fake_dispatcher)
    monkeypatch.setattr(auxiliary_client, "call_llm", broken_reviewer)
    monkeypatch.setattr(auxiliary_client, "extract_content_or_reasoning", lambda value: value)

    dispatch = await governance_pre_gateway_dispatch(
        event=_Event("수시 점수 계산 파일 첨부해서 보내줘"),
        gateway=_Gateway(),
    )
    assert dispatch["intent"] == "discord_attachment_delivery"
    assert dispatch["routing_source"] == "miho_governance_dispatcher"

    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        result=json.dumps(
            {
                "success": True,
                "artifact_path": "/tmp/report.mhtml",
                "semantic_review_required": True,
                "reviewer": {
                    "name": "attachment_delivery_review",
                    "status": "pass",
                    "checked": ["media_tag", "artifact_path"],
                },
            },
            ensure_ascii=False,
        ),
        governance_skip_ledger=True,
    )

    assert transformed is not None
    payload = json.loads(transformed)
    assert payload["success"] is False
    user_text = payload["error"]
    assert "의미 검증" in user_text
    assert "provider offline" not in user_text
    assert "miho_governance_reviewer" not in user_text
    assert "Traceback" not in user_text
