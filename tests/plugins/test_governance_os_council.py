"""Agent Council execution contract tests for Governance OS."""

from __future__ import annotations

import importlib
import json

from plugins.governance_os.council import run_council_turn
from plugins.governance_os.registry import load_builtin_registry


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


def _reload_evolution_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants
    from agent import evolution

    importlib.reload(miho_constants)
    importlib.reload(evolution)
    return evolution


def test_council_records_research_review_pass_outcome(tmp_path, monkeypatch) -> None:
    calls = _patch_auxiliary_review_pass(monkeypatch)
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    result = run_council_turn(
        registry=load_builtin_registry(),
        request_id="req-research-1",
        user_text="최신 입시 정책 조사해줘",
        available_context=("source_attribution", "date_sensitivity", "user_question"),
        tool_name="web_search",
        tool_result=json.dumps(
            {
                "ok": True,
                "reviewer": {
                    "name": "source_attribution_review",
                    "status": "pass",
                    "checked": ["source_attribution"],
                },
            }
        ),
    )

    assert result.status == "passed"
    assert result.playbook_key == "research_brief"
    assert result.ledger_event is not None
    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["request_id"] == "req-research-1"
    assert outcome["tools_used"] == ["web_search"]
    assert outcome["review_status"] == "pass"
    assert outcome["failures"] == []
    assert calls


def test_council_blocks_forbidden_tool_and_records_failure(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    result = run_council_turn(
        registry=load_builtin_registry(),
        request_id="req-hakjong-block",
        user_text="서연이 학종 리포트 PDF 만들어줘",
        tool_name="write_file",
        tool_result={"ok": True},
    )

    assert result.status == "blocked"
    assert result.action == "block"
    assert "전용 도구" in result.message_ko
    assert result.ledger_event is not None
    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["playbook_key"] == "academy_hakjong_report"
    assert outcome["review_status"] == "blocked"
    assert outcome["failures"] == ["forbidden_tool"]


def test_council_review_failure_requests_retry_and_records_failure(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    result = run_council_turn(
        registry=load_builtin_registry(),
        request_id="req-discord-retry",
        user_text="mhtml 파일 첨부가 안돼",
        tool_name="media_delivery_contract",
        tool_result={"ok": True},
    )

    assert result.status == "retry"
    assert result.action == "retry"
    assert "후검증" in result.message_ko
    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["playbook_key"] == "discord_attachment_delivery"
    assert outcome["review_status"] == "fail"
    assert outcome["failures"] == ["reviewer_missing"]


def test_council_records_review_required_hold_before_result(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    result = run_council_turn(
        registry=load_builtin_registry(),
        request_id="req-discord-hold",
        user_text="엑셀 파일 첨부해서 보내줘",
        available_context=("media_tag", "artifact_path", "channel_permission"),
        tool_name="media_delivery_contract",
        tool_result=None,
    )

    assert result.status == "review_required"
    assert result.action == "hold"
    assert result.ledger_event is not None
    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["request_id"] == "req-discord-hold"
    assert outcome["playbook_key"] == "discord_attachment_delivery"
    assert outcome["review_status"] == "review_required"
    assert outcome["tools_used"] == ["media_delivery_contract"]
    assert outcome["failures"] == []


def test_council_records_discord_attachment_review_pass(tmp_path, monkeypatch) -> None:
    calls = _patch_auxiliary_review_pass(monkeypatch)
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    result = run_council_turn(
        registry=load_builtin_registry(),
        request_id="req-discord-pass",
        user_text="엑셀 파일 첨부해서 보내줘",
        available_context=("media_tag", "artifact_path", "channel_permission"),
        tool_name="media_delivery_contract",
        tool_result=json.dumps(
            {
                "success": True,
                "artifact_path": "/tmp/report.xlsx",
                "media_tag": "MEDIA:/tmp/report.xlsx",
                "reviewer": {
                    "name": "attachment_delivery_review",
                    "status": "pass",
                    "checked": ["media_tag", "artifact_path"],
                },
            }
        ),
        artifact_paths=("/tmp/report.xlsx",),
    )

    assert result.status == "passed"
    assert result.action == "deliver"
    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["playbook_key"] == "discord_attachment_delivery"
    assert outcome["tools_used"] == ["media_delivery_contract"]
    assert outcome["review_status"] == "pass"
    assert outcome["artifact_paths"] == ["/tmp/report.xlsx"]
    assert calls
    assert calls[0]["task"] == "miho_governance_reviewer_delivery"


def test_council_requires_approval_for_high_risk_deploy_request(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    result = run_council_turn(
        registry=load_builtin_registry(),
        request_id="req-dev-approval",
        user_text="프로덕션 배포하고 게이트웨이 재시작해줘",
        available_context=("repo_root", "tests_required", "rollback_plan"),
        tool_name="apply_patch",
        tool_result=None,
    )

    assert result.status == "approval_required"
    assert result.action == "hold"
    assert "승인" in result.message_ko
    assert result.ledger_event is not None
    outcome = evolution.list_events(limit=1)[0]["metadata"]["governance_outcome"]
    assert outcome["playbook_key"] == "dev_code_update"
    assert outcome["review_status"] == "approval_required"
    assert outcome["failures"] == ["approval_required"]


def test_council_allows_unmatched_request_without_ledger(tmp_path, monkeypatch) -> None:
    evolution = _reload_evolution_home(tmp_path, monkeypatch)

    result = run_council_turn(
        registry=load_builtin_registry(),
        request_id="req-general",
        user_text="오늘 점심 뭐 먹지",
        tool_name="noop",
        tool_result={"ok": True},
    )

    assert result.status == "allowed"
    assert result.ledger_event is None
    assert evolution.list_events(limit=1) == []
