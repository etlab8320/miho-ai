"""Final Delivery retry executor coverage."""

from __future__ import annotations

import json
from typing import Any

from plugins.governance_os.delivery_gate import governance_transform_llm_output


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


def test_final_delivery_retry_executor_reruns_tool_from_current_turn_args(monkeypatch) -> None:
    _patch_academy_auxiliary_pass(monkeypatch)
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_dispatch(name: str, args: dict[str, Any], **_kwargs: object) -> str:
        calls.append((name, args))
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

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)
    monkeypatch.setattr(
        "plugins.governance_os.review._call_auxiliary_reviewer",
        lambda **_kwargs: {
            "status": "pass",
            "checked": ["media_tag", "artifact_path"],
        },
    )

    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 980.0점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
        conversation_history=[
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
            {
                "role": "tool",
                "name": "susi27_score_calculate",
                "tool_call_id": "call-score",
                "content": json.dumps({"success": True}, ensure_ascii=False),
            },
        ],
        final_delivery_call_llm=_broken_llm,
        final_delivery_extract_content=_extract,
    )

    assert transformed is not None
    assert "947.3점" in transformed
    assert "980.0" not in transformed
    assert "확인한 뒤" not in transformed
    assert "후검증" not in transformed
    assert calls == [
        (
            "susi27_score_calculate",
            {
                "student_name": "김서연",
                "university": "테스트대학교",
                "department": "체육학과",
            },
        )
    ]


def test_final_delivery_retry_executor_uses_retry_args_from_review_payload(monkeypatch) -> None:
    _patch_academy_auxiliary_pass(monkeypatch)
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_dispatch(name: str, args: dict[str, Any], **_kwargs: object) -> str:
        calls.append((name, args))
        return json.dumps(
            {
                "success": True,
                "artifact_path": "/tmp/report.pdf",
                "media_tag": "MEDIA:/tmp/report.pdf",
                "reviewer": {
                    "name": "attachment_delivery_review",
                    "status": "pass",
                    "checked": ["media_tag", "artifact_path"],
                },
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)

    transformed = governance_transform_llm_output(
        response_text="MHTML 파일을 첨부했습니다.",
        user_message="mhtml 파일 첨부해서 보내줘",
        governance_outcomes=[],
        conversation_history=[
            {"role": "user", "content": "mhtml 파일 첨부해서 보내줘"},
            {
                "role": "tool",
                "name": "media_delivery_contract",
                "content": json.dumps(
                    {
                        "success": False,
                        "governance_review": {
                            "retry_args": [{"artifact_path": "/tmp/report.pdf"}]
                        },
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        final_delivery_call_llm=_broken_llm,
        final_delivery_extract_content=_extract,
    )

    assert transformed is not None
    assert "MEDIA:/tmp/report.pdf" in transformed
    assert "첨부했습니다" not in transformed
    assert calls == [("media_delivery_contract", {"artifact_path": "/tmp/report.pdf"})]


def test_final_delivery_orchestrator_builds_retry_plan_when_args_missing(monkeypatch) -> None:
    _patch_academy_auxiliary_pass(monkeypatch)
    tool_calls: list[tuple[str, dict[str, Any]]] = []
    orchestrator_calls: list[dict[str, Any]] = []

    def fake_dispatch(name: str, args: dict[str, Any], **_kwargs: object) -> str:
        tool_calls.append((name, args))
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

    def fake_orchestrator_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        orchestrator_calls.append(kwargs)
        prompt = str(kwargs["messages"][1]["content"])
        mode = str(json.loads(prompt).get("mode") or "")
        if mode == "compose_answer":
            return {
                "content": json.dumps(
                    {
                        "action": "deliver",
                        "answer": "계산 결과는 947.3점입니다.",
                    },
                    ensure_ascii=False,
                )
            }
        return {
            "content": json.dumps(
                {
                    "action": "run_tools",
                    "steps": [
                        {
                            "tool_name": "susi27_score_calculate",
                            "args": {
                                "student_name": "김서연",
                                "university": "테스트대학교",
                                "department": "체육학과",
                            },
                        }
                    ],
                    "reason": "current question contains enough score calculation intent",
                },
                ensure_ascii=False,
            )
        }

    def final_delivery_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        task = str(kwargs.get("task") or "")
        if task == "miho_governance_final_delivery":
            return {
                "content": json.dumps(
                    {
                        "action": "deliver",
                        "answer": "계산 결과는 947.3점입니다.",
                    },
                    ensure_ascii=False,
                )
            }
        raise AssertionError(f"unexpected task: {task}")

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)

    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 980.0점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
        conversation_history=[
            {"role": "user", "content": "서연이 수시 환산점수 계산해줘"},
        ],
        final_delivery_orchestrator_call_llm=fake_orchestrator_llm,
        final_delivery_orchestrator_extract_content=_extract,
        final_delivery_call_llm=final_delivery_llm,
        final_delivery_extract_content=_extract,
    )

    assert transformed == "계산 결과는 947.3점입니다."
    assert orchestrator_calls
    assert orchestrator_calls[0]["task"] == "miho_governance_final_delivery_orchestrator"
    assert tool_calls == [
        (
            "susi27_score_calculate",
            {
                "student_name": "김서연",
                "university": "테스트대학교",
                "department": "체육학과",
            },
        )
    ]


def test_final_delivery_orchestrator_composes_answer_after_verified_retry(
    monkeypatch,
) -> None:
    _patch_academy_auxiliary_pass(monkeypatch)
    tool_calls: list[tuple[str, dict[str, Any]]] = []
    orchestrator_modes: list[str] = []

    def fake_dispatch(name: str, args: dict[str, Any], **_kwargs: object) -> str:
        tool_calls.append((name, args))
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

    def fake_orchestrator_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        prompt = kwargs["messages"][1]["content"]
        assert isinstance(prompt, str)
        payload = json.loads(prompt)
        mode = str(payload.get("mode") or "")
        orchestrator_modes.append(mode)
        if mode == "plan_tools":
            return {
                "content": json.dumps(
                    {
                        "action": "run_tools",
                        "steps": [
                            {
                                "tool_name": "susi27_score_calculate",
                                "args": {
                                    "student_name": "김서연",
                                    "university": "테스트대학교",
                                    "department": "체육학과",
                                },
                            }
                        ],
                        "reason": "question has enough score calculation context",
                    },
                    ensure_ascii=False,
                )
            }
        if mode == "compose_answer":
            assert payload["verified_tool_results"][0]["tool_name"] == "susi27_score_calculate"
            return {
                "content": json.dumps(
                    {
                        "action": "deliver",
                        "answer": "서연이 수시 환산점수는 947.3점입니다.",
                    },
                    ensure_ascii=False,
                )
            }
        raise AssertionError(f"unexpected orchestrator mode: {mode}")

    def final_delivery_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        prompt = str(kwargs["messages"][-1]["content"])
        answer = prompt.split("\nEVIDENCE: ", 1)[0].split("\nA: ", 1)[1]
        return {
            "content": json.dumps(
                {"action": "deliver", "answer": answer},
                ensure_ascii=False,
            )
        }

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)

    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 980.0점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
        conversation_history=[
            {"role": "user", "content": "서연이 수시 환산점수 계산해줘"},
        ],
        final_delivery_orchestrator_call_llm=fake_orchestrator_llm,
        final_delivery_orchestrator_extract_content=_extract,
        final_delivery_call_llm=final_delivery_llm,
        final_delivery_extract_content=_extract,
    )

    assert transformed == "서연이 수시 환산점수는 947.3점입니다."
    assert orchestrator_modes == ["plan_tools", "compose_answer"]
    assert tool_calls == [
        (
            "susi27_score_calculate",
            {
                "student_name": "김서연",
                "university": "테스트대학교",
                "department": "체육학과",
            },
        )
    ]


def test_final_delivery_orchestrator_falls_back_to_default_transport(
    monkeypatch,
) -> None:
    _patch_academy_auxiliary_pass(monkeypatch)
    tool_calls: list[tuple[str, dict[str, Any]]] = []
    default_modes: list[str] = []

    def fake_dispatch(name: str, args: dict[str, Any], **_kwargs: object) -> str:
        tool_calls.append((name, args))
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

    def broken_orchestrator_llm(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("primary orchestrator transport down")

    def default_orchestrator_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        prompt = kwargs["messages"][1]["content"]
        assert isinstance(prompt, str)
        mode = str(json.loads(prompt).get("mode") or "")
        default_modes.append(mode)
        if mode == "plan_tools":
            return {
                "content": json.dumps(
                    {
                        "action": "run_tools",
                        "steps": [
                            {
                                "tool_name": "susi27_score_calculate",
                                "args": {
                                    "student_name": "김서연",
                                    "university": "테스트대학교",
                                    "department": "체육학과",
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                )
            }
        return {
            "content": json.dumps(
                {
                    "action": "deliver",
                    "answer": "서연이 수시 환산점수는 947.3점입니다.",
                },
                ensure_ascii=False,
            )
        }

    def final_delivery_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        prompt = str(kwargs["messages"][-1]["content"])
        answer = prompt.split("\nEVIDENCE: ", 1)[0].split("\nA: ", 1)[1]
        return {"content": json.dumps({"action": "deliver", "answer": answer}, ensure_ascii=False)}

    monkeypatch.setattr("tools.registry.registry.dispatch", fake_dispatch)
    monkeypatch.setattr("agent.auxiliary_client.call_llm", default_orchestrator_llm)
    monkeypatch.setattr("agent.auxiliary_client.extract_content_or_reasoning", _extract)

    transformed = governance_transform_llm_output(
        response_text="서연이 수시 환산점수는 980.0점입니다.",
        user_message="서연이 수시 환산점수 계산해줘",
        governance_outcomes=[],
        conversation_history=[
            {"role": "user", "content": "서연이 수시 환산점수 계산해줘"},
        ],
        final_delivery_orchestrator_call_llm=broken_orchestrator_llm,
        final_delivery_orchestrator_extract_content=_extract,
        final_delivery_call_llm=final_delivery_llm,
        final_delivery_extract_content=_extract,
    )

    assert transformed == "서연이 수시 환산점수는 947.3점입니다."
    assert default_modes == ["plan_tools", "compose_answer"]
    assert tool_calls == [
        (
            "susi27_score_calculate",
            {
                "student_name": "김서연",
                "university": "테스트대학교",
                "department": "체육학과",
            },
        )
    ]
