"""No-hardcoded-answer coverage for Final Delivery retry."""

from __future__ import annotations

import json
from typing import Any

from plugins.governance_os.final_delivery_retry import retry_blocked_final_delivery
from plugins.governance_os.versioning import load_runtime_registry


def _broken_llm(*_args: object, **_kwargs: object) -> object:
    raise RuntimeError("auxiliary unavailable")


def _extract(response: object) -> str:
    if isinstance(response, dict):
        return str(response.get("content") or "")
    return str(response or "")


def _patch_academy_auxiliary_pass(monkeypatch) -> None:
    import plugins.governance_os.review as review

    def fake_auxiliary_reviewer(**kwargs: object) -> dict[str, object]:
        checked = kwargs.get("checked")
        return {
            "status": "pass",
            "checked": list(checked) if isinstance(checked, (list, tuple)) else [],
        }

    monkeypatch.setattr(review, "_call_auxiliary_reviewer", fake_auxiliary_reviewer)


def test_final_delivery_retry_does_not_synthesize_score_text_without_agent(
    monkeypatch,
) -> None:
    _patch_academy_auxiliary_pass(monkeypatch)

    def fake_dispatch(name: str, args: dict[str, Any], **_kwargs: object) -> str:
        assert name == "susi27_score_calculate"
        assert args == {
            "student_name": "김서연",
            "university": "테스트대학교",
            "department": "체육학과",
        }
        return _score_payload()

    result = retry_blocked_final_delivery(
        registry=load_runtime_registry(),
        playbook_key="susi_score_calculation",
        retry_tools=("susi27_score_calculate",),
        question="서연이 수시 환산점수 계산해줘",
        conversation_history=_score_tool_call_history(),
        dispatch_tool=fake_dispatch,
        orchestrator_call_llm=_broken_llm,
        orchestrator_extract_content=_extract,
    )

    assert result is None


def test_final_delivery_retry_without_orchestrator_rejects_score_only_payload(
    monkeypatch,
) -> None:
    _patch_academy_auxiliary_pass(monkeypatch)

    def fake_dispatch(name: str, args: dict[str, Any], **_kwargs: object) -> str:
        return _score_payload()

    result = retry_blocked_final_delivery(
        registry=load_runtime_registry(),
        playbook_key="susi_score_calculation",
        retry_tools=("susi27_score_calculate",),
        question="서연이 수시 환산점수 계산해줘",
        conversation_history=_score_tool_call_history(),
        dispatch_tool=fake_dispatch,
    )

    assert result is None


def _score_payload() -> str:
    return json.dumps(
        {
            "status": "calculated",
            "student_record_score": 947.3,
            "reviewer": {
                "name": "academy_result_reviewer",
                "status": "pass",
                "checked": ["필수 산출 필드", "상태값"],
            },
        },
        ensure_ascii=False,
    )


def _score_tool_call_history() -> list[dict[str, object]]:
    return [
        {"role": "user", "content": "서연이 수시 환산점수 계산해줘"},
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "call-score",
                    "type": "function",
                    "function": {
                        "name": "susi27_score_calculate",
                        "arguments": json.dumps(
                            {
                                "student_name": "김서연",
                                "university": "테스트대학교",
                                "department": "체육학과",
                            },
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        },
    ]
