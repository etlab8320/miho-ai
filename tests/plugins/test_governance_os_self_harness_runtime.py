"""Runtime feedback loop tests for Governance OS Self-Harness."""

from __future__ import annotations

import importlib
import json
from typing import Any, cast

from plugins.governance_os.self_harness_loop import PROPOSER_TASK, WEAKNESS_MINER_TASK


def _reload_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))

    import miho_constants
    from agent import evolution

    importlib.reload(miho_constants)
    importlib.reload(evolution)
    return evolution


def _all_pass(_test_path: str) -> tuple[int, str]:
    return 0, "passed"


def _all_fail(_test_path: str) -> tuple[int, str]:
    return 1, "failed after activation"


def _extract(response: object) -> str:
    assert isinstance(response, dict)
    typed = cast("dict[str, object]", response)
    return str(typed.get("content") or "")


def _agentic_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
    task = str(kwargs.get("task") or "")
    messages = kwargs.get("messages")
    assert isinstance(messages, list)
    user_message = messages[1]
    assert isinstance(user_message, dict)
    user_payload = json.loads(str(user_message.get("content") or ""))
    if task == WEAKNESS_MINER_TASK:
        payload = user_payload["deterministic_bundle"]
    else:
        payload = {"candidates": user_payload["deterministic_candidates"]}
    return {"content": json.dumps(payload, ensure_ascii=False)}


def _prior_event(event_id: int = 1) -> dict[str, Any]:
    return {
        "id": event_id,
        "metadata": {
            "governance_outcome": {
                "request_id": f"prior-{event_id}",
                "playbook_key": "designed_pdf_artifact",
                "review_status": "user_reported_failure",
                "failures": ["pdf_footer_overflow"],
                "artifact_paths": ["/tmp/bad.pdf"],
                "user_feedback": "푸터가 밀렸다",
            }
        },
    }


def test_runtime_feedback_loop_records_feedback_and_activates(tmp_path, monkeypatch) -> None:
    evolution = _reload_home(tmp_path, monkeypatch)

    from miho_cli.owner_profile import list_profile_events
    from miho_cli.owner_profile import DAILY_SUMMARY_JOB_NAME
    from miho_cli.skill_curator import DAILY_SKILL_REVIEW_JOB_NAME, list_skill_candidates
    from plugins.governance_os.self_harness_runtime import run_feedback_improvement_loop

    result = run_feedback_improvement_loop(
        request_id="feedback-runtime-1",
        playbook_key="designed_pdf_artifact",
        failure_signature="pdf_footer_overflow",
        user_feedback="PDF 푸터가 페이지 밖으로 밀렸어",
        artifact_paths=("/tmp/bad.pdf",),
        recent_events=(_prior_event(),),
        receipt_runner=_all_pass,
        smoke_runner=_all_pass,
        call_llm=_agentic_call_llm,
        extract_content=_extract,
    )

    assert result["schema_version"] == "miho-self-harness/runtime-feedback-loop/v1"
    assert result["status"] == "activated"
    assert result["self_harness_triggered"] is True
    assert result["user_visible_message_allowed"] is False
    assert result["recorded_event_id"]
    assert result["autopilot"]["activated"]
    assert not result["autopilot"]["held"]
    outcomes = [
        item["metadata"]["governance_outcome"]
        for item in evolution.list_events(limit=10)
        if "governance_outcome" in item.get("metadata", {})
    ]
    assert any(item["user_feedback"] == "PDF 푸터가 페이지 밖으로 밀렸어" for item in outcomes)
    profile_events = list_profile_events(limit=5, category="miho_self_harness")
    assert profile_events
    assert "PDF 푸터가 페이지 밖으로 밀렸어" in profile_events[0]["content"]
    candidates = list_skill_candidates(status="pending", kind="failure_pattern", limit=5)
    assert candidates
    assert candidates[0]["source"] == "governance_os.self_harness_runtime"
    assert candidates[0]["hits"] == 1
    assert "designed_pdf_artifact" in candidates[0]["summary"]
    assert "pdf_footer_overflow" in candidates[0]["evidence"]
    from cron.jobs import load_jobs

    job_names = {str(job.get("name") or "") for job in load_jobs()}
    assert DAILY_SUMMARY_JOB_NAME in job_names
    assert DAILY_SKILL_REVIEW_JOB_NAME in job_names


def test_runtime_feedback_loop_rolls_back_on_regression(tmp_path, monkeypatch) -> None:
    _reload_home(tmp_path, monkeypatch)

    from plugins.governance_os.self_harness_runtime import run_feedback_improvement_loop

    result = run_feedback_improvement_loop(
        request_id="feedback-runtime-rollback",
        playbook_key="designed_pdf_artifact",
        failure_signature="pdf_footer_overflow",
        user_feedback="PDF 푸터가 또 밀렸어",
        recent_events=(_prior_event(),),
        receipt_runner=_all_pass,
        smoke_runner=_all_fail,
        call_llm=_agentic_call_llm,
        extract_content=_extract,
    )

    assert result["status"] == "rolled_back"
    assert result["autopilot"]["rolled_back"]
    assert result["autopilot"]["rolled_back"][0]["reason"] == "post_activation_regression"


def test_runtime_feedback_loop_holds_one_off_feedback(tmp_path, monkeypatch) -> None:
    _reload_home(tmp_path, monkeypatch)

    from plugins.governance_os.self_harness_runtime import run_feedback_improvement_loop

    result = run_feedback_improvement_loop(
        request_id="feedback-runtime-one-off",
        playbook_key="designed_pdf_artifact",
        failure_signature="pdf_footer_overflow",
        user_feedback="PDF 푸터가 한 번 밀렸어",
        recent_events=(),
        receipt_runner=_all_pass,
        smoke_runner=_all_pass,
        call_llm=_agentic_call_llm,
        extract_content=_extract,
    )

    assert result["status"] == "held"
    assert result["recorded_event_id"]
    assert result["autopilot"]["candidate_count"] == 0
