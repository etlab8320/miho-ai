"""Review retry contract tests for Governance OS."""

from __future__ import annotations

import importlib
import json

from plugins.governance_os.council import run_council_turn
from plugins.governance_os.registry import load_builtin_registry
from plugins.governance_os.result_transform import governance_transform_tool_result
from plugins.governance_os.review import auxiliary_review_policy_for_playbook, evaluate_review_gate


def _patch_auxiliary_review_pass(monkeypatch) -> list[dict[str, object]]:
    import plugins.governance_os.review as review

    calls: list[dict[str, object]] = []

    def fake_auxiliary_reviewer(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        checked = kwargs.get("checked")
        return {
            "status": "pass",
            "checked": list(checked) if isinstance(checked, (list, tuple)) else [],
        }

    monkeypatch.setattr(review, "_call_auxiliary_reviewer", fake_auxiliary_reviewer)
    return calls


def _patch_auxiliary_review_broken(monkeypatch) -> list[dict[str, object]]:
    import plugins.governance_os.review as review

    calls: list[dict[str, object]] = []

    def broken_auxiliary_reviewer(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        raise RuntimeError("provider offline")

    monkeypatch.setattr(review, "_call_auxiliary_reviewer", broken_auxiliary_reviewer)
    return calls


def _reload_evolution_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants
    from agent import evolution

    importlib.reload(miho_constants)
    importlib.reload(evolution)
    return evolution


def test_review_failure_returns_required_retry_tools() -> None:
    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        result=json.dumps({"ok": True, "file_path": "/tmp/report.pdf"}),
    )

    assert outcome.status == "fail"
    assert outcome.reason == "reviewer_missing"
    assert outcome.retry_tools == ("academy_hakjong_report_package",)
    assert "retry_tools" not in outcome.retry_instruction_ko
    assert "전용 도구" in outcome.retry_instruction_ko


def test_review_gate_accepts_academy_reviewer_pass_payload() -> None:
    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        result=json.dumps(
            {
                "ok": True,
                "reviewer": {
                    "name": "academy_result_reviewer",
                    "status": "pass",
                    "checked": ["레이아웃", "산식"],
                },
            },
            ensure_ascii=False,
        ),
    )

    assert outcome.status == "pass"
    assert outcome.reason == "reviewer_pass"
    assert "academy_result_reviewer" in outcome.gate_names


def test_academy_reviewer_pass_requires_meaningful_checked_items() -> None:
    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        result=json.dumps(
            {
                "ok": True,
                "reviewer": {
                    "name": "academy_result_reviewer",
                    "status": "pass",
                    "checked": [],
                },
            },
            ensure_ascii=False,
        ),
    )

    assert outcome.status == "fail"
    assert outcome.reason == "reviewer_missing_required_checks"
    assert outcome.retry_tools == ("academy_hakjong_report_package",)


def test_review_gate_fails_missing_reviewer_for_reviewed_tool() -> None:
    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        result=json.dumps({"ok": True, "file_path": "/tmp/report.pdf"}),
    )

    assert outcome.status == "fail"
    assert outcome.reason == "reviewer_missing"
    assert "후검증" in outcome.message_ko


def test_review_gate_passes_non_reviewed_tool_without_reviewer() -> None:
    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="life_record_search",
        result=json.dumps({"ok": True}),
    )

    assert outcome.status == "pass"
    assert outcome.reason == "no_review_required"


def test_runtime_review_policy_requires_llm_reviewer_for_governed_playbooks() -> None:
    assert auxiliary_review_policy_for_playbook("discord_attachment_delivery") == "always"
    assert auxiliary_review_policy_for_playbook("dev_code_update") == "always"
    assert auxiliary_review_policy_for_playbook("academy_hakjong_report") == "always"


def test_review_gate_calls_auxiliary_reviewer_for_semantic_risk(monkeypatch) -> None:
    import plugins.governance_os.review as review

    calls: list[dict[str, object]] = []

    def fake_auxiliary_reviewer(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "status": "pass",
            "reason": "semantic_review_passed",
            "checked": ["레이아웃", "산식"],
        }

    monkeypatch.setattr(
        review,
        "_call_auxiliary_reviewer",
        fake_auxiliary_reviewer,
        raising=False,
    )

    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        result=json.dumps(
            {
                "ok": True,
                "semantic_review_required": True,
                "reviewer": {
                    "name": "academy_result_reviewer",
                    "status": "pass",
                    "checked": ["레이아웃", "산식"],
                },
            },
            ensure_ascii=False,
        ),
    )

    assert calls
    assert calls[0]["task"] == "miho_governance_reviewer_academy"
    assert outcome.status == "pass"
    assert outcome.reason == "auxiliary_reviewer_pass"


def test_review_gate_fails_closed_when_auxiliary_reviewer_unavailable(monkeypatch) -> None:
    import plugins.governance_os.review as review

    def broken_auxiliary_reviewer(**_: object) -> dict[str, object]:
        raise RuntimeError("provider offline")

    monkeypatch.setattr(
        review,
        "_call_auxiliary_reviewer",
        broken_auxiliary_reviewer,
        raising=False,
    )

    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="academy_hakjong_report",
        tool_name="academy_hakjong_report_package",
        result=json.dumps(
            {
                "ok": True,
                "semantic_review_required": True,
                "reviewer": {
                    "name": "academy_result_reviewer",
                    "status": "pass",
                    "checked": ["레이아웃", "산식"],
                },
            },
            ensure_ascii=False,
        ),
    )

    assert outcome.status == "fail"
    assert outcome.reason == "auxiliary_reviewer_unavailable"
    assert "의미 검증" in outcome.message_ko
    assert "provider offline" not in outcome.message_ko
    assert "miho_governance_reviewer" not in outcome.message_ko


def test_auxiliary_reviewer_uses_agent_auxiliary_client_without_semantic_flag(monkeypatch) -> None:
    import agent.auxiliary_client as auxiliary_client

    calls: list[dict[str, object]] = []

    def fake_call_llm(**kwargs: object) -> str:
        calls.append(kwargs)
        return json.dumps(
            {
                "status": "pass",
                "checked": ["필수 산출 필드", "상태값"],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(auxiliary_client, "call_llm", fake_call_llm)
    monkeypatch.setattr(auxiliary_client, "extract_content_or_reasoning", lambda value: value)

    outcome = evaluate_review_gate(
        load_builtin_registry(),
        playbook_key="susi_score_calculation",
        tool_name="susi27_score_calculate",
        result=json.dumps(
            {
                "success": True,
                "student_record_score": 947.3,
                "reviewer": {
                    "name": "academy_result_reviewer",
                    "status": "pass",
                    "checked": ["필수 산출 필드", "상태값"],
                },
            },
            ensure_ascii=False,
        ),
        auxiliary_review_policy="always",
    )

    assert outcome.status == "pass"
    assert outcome.reason == "auxiliary_reviewer_pass"
    assert calls
    assert calls[0]["task"] == "miho_governance_reviewer_academy"
    assert calls[0]["timeout"] == 15
    user_payload = json.loads(calls[0]["messages"][1]["content"])  # type: ignore[index]
    assert user_payload["tool_name"] == "susi27_score_calculate"
    assert user_payload["payload"]["student_record_score"] == 947.3


def test_transform_failure_exposes_retry_tools() -> None:
    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
    )

    assert transformed is not None
    payload = json.loads(transformed)
    assert payload["next_action"] == "retry_required"
    assert "media_delivery_contract" not in payload["error"]
    assert payload["governance_review"]["retry_tools"] == ["media_delivery_contract"]
    assert "retry_tools" not in payload["governance_review"]["retry_instruction_ko"]
    assert "전용 도구" in payload["governance_review"]["retry_instruction_ko"]


def test_governance_transform_blocks_self_reviewed_tool_without_reviewer() -> None:
    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
    )

    assert transformed is not None
    payload = json.loads(transformed)
    assert payload["success"] is False
    assert "후검증" in payload["error"]


def test_governance_transform_separates_internal_and_user_safe_layers() -> None:
    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
    )

    assert transformed is not None
    payload = json.loads(transformed)
    # 내부 전용 지시 레이어: 재시도 지시문 유지.
    assert payload["assistant_instruction"] == payload["error"]
    # 사용자 노출 레이어: 내부 지시 용어가 새지 않아야 한다.
    user_safe = payload["user_safe_message"]
    assert "후검증" not in user_safe
    assert "전용 도구" not in user_safe
    assert "retry" not in user_safe.casefold()
    assert user_safe.strip()


def test_governance_transform_calls_auxiliary_reviewer_without_semantic_flag(monkeypatch) -> None:
    calls = _patch_auxiliary_review_pass(monkeypatch)

    transformed = governance_transform_tool_result(
        tool_name="susi27_score_calculate",
        result=json.dumps(
            {
                "success": True,
                "student_record_score": 947.3,
                "reviewer": {
                    "name": "academy_result_reviewer",
                    "status": "pass",
                    "checked": ["필수 산출 필드", "상태값"],
                },
            },
            ensure_ascii=False,
        ),
    )

    assert transformed is None
    assert calls
    assert calls[0]["task"] == "miho_governance_reviewer_academy"
    assert calls[0]["tool_name"] == "susi27_score_calculate"


def test_governance_transform_calls_auxiliary_reviewer_for_attachment_delivery(
    monkeypatch,
) -> None:
    calls = _patch_auxiliary_review_pass(monkeypatch)

    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        result=json.dumps(
            {
                "success": True,
                "reviewer": {
                    "name": "attachment_delivery_review",
                    "status": "pass",
                    "checked": ["media_tag", "artifact_path"],
                },
            }
        ),
    )

    assert transformed is None
    assert calls
    assert calls[0]["task"] == "miho_governance_reviewer_delivery"


def test_governance_transform_failure_records_outcome_ledger(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        result=json.dumps({"success": True, "artifact_path": "/tmp/report.mhtml"}),
        tool_call_id="call-media-fail",
        duration_ms=17,
    )

    assert transformed is not None
    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["request_id"] == "call-media-fail"
    assert outcome["playbook_key"] == "discord_attachment_delivery"
    assert outcome["tools_used"] == ["media_delivery_contract"]
    assert outcome["duration_ms"] == 17
    assert outcome["review_status"] == "fail"
    assert outcome["failures"] == ["reviewer_missing"]
    assert outcome["retry_tools"] == ["media_delivery_contract"]
    assert outcome["artifact_paths"] == ["/tmp/report.mhtml"]


def test_governance_transform_pass_records_outcome_ledger(tmp_path, monkeypatch) -> None:
    _patch_auxiliary_review_pass(monkeypatch)

    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    transformed = governance_transform_tool_result(
        tool_name="media_delivery_contract",
        result=json.dumps(
            {
                "success": True,
                "artifact_path": "/tmp/report.mhtml",
                "media_tag": "MEDIA:/tmp/report.mhtml",
                "reviewer": {
                    "name": "attachment_delivery_review",
                    "status": "pass",
                    "checked": ["media_tag", "artifact_path"],
                },
            }
        ),
        tool_call_id="call-media-pass",
        duration_ms=23,
    )

    assert transformed is None
    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["request_id"] == "call-media-pass"
    assert outcome["playbook_key"] == "discord_attachment_delivery"
    assert outcome["tools_used"] == ["media_delivery_contract"]
    assert outcome["duration_ms"] == 23
    assert outcome["review_status"] == "pass"
    assert outcome["failures"] == []
    assert outcome["artifact_paths"] == ["/tmp/report.mhtml"]


def test_council_calls_auxiliary_reviewer_for_attachment_pass(monkeypatch) -> None:
    calls = _patch_auxiliary_review_pass(monkeypatch)

    result = run_council_turn(
        registry=load_builtin_registry(),
        request_id="req-discord-pass",
        user_text="mhtml 파일 첨부해서 보내줘",
        tool_name="media_delivery_contract",
        tool_result={
            "success": True,
            "artifact_path": "/tmp/report.mhtml",
            "media_tag": "MEDIA:/tmp/report.mhtml",
            "reviewer": {
                "name": "attachment_delivery_review",
                "status": "pass",
                "checked": ["media_tag", "artifact_path"],
            },
        },
        record_ledger=False,
    )

    assert result.status == "passed"
    assert calls
    assert calls[0]["task"] == "miho_governance_reviewer_delivery"


def test_council_retry_records_retry_tools_in_ledger(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    result = run_council_turn(
        registry=load_builtin_registry(),
        request_id="req-discord-retry-tools",
        user_text="mhtml 파일 첨부가 안돼",
        tool_name="media_delivery_contract",
        tool_result={"ok": True},
    )

    assert result.status == "retry"
    assert result.retry_tools == ("media_delivery_contract",)
    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["retry_tools"] == ["media_delivery_contract"]
