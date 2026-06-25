"""Tests for the autonomous Self-Harness improvement loop."""

from __future__ import annotations

import json
from typing import Any, cast

import plugins.governance_os.self_harness_loop as loop


class _Activation:
    snapshot_id = "snap-new"
    rollback_snapshot_id = "snap-old"
    event_id = 7
    playbook_key = "academy_hakjong_report"
    action = "add_review_gate"
    value = "domain_reviewer"
    fingerprint = "fp"


def _events(failure: str, *, playbook: str = "academy_hakjong_report", n: int = 2) -> list[dict[str, Any]]:
    return [
        {
            "id": index,
            "metadata": {
                "governance_outcome": {
                    "playbook_key": playbook,
                    "failures": [failure],
                    "request_id": f"req-{index}",
                    "review_status": "fail",
                }
            },
        }
        for index in range(n)
    ]


def _all_pass(_test_path: str) -> tuple[int, str]:
    return 0, "passed"


def _all_fail(_test_path: str) -> tuple[int, str]:
    return 1, "1 failed"


def test_generate_test_receipts_marks_pass_and_fail() -> None:
    candidate = _candidate("final_qa answer mismatch")

    passed = loop.generate_test_receipts(candidate, runner=_all_pass)
    assert passed and all(receipt["status"] == "passed" for receipt in passed)
    assert all(receipt["exit_code"] == 0 for receipt in passed)

    failed = loop.generate_test_receipts(candidate, runner=_all_fail)
    assert failed and all(receipt["status"] == "failed" for receipt in failed)


def test_autopilot_activates_when_receipts_and_smoke_pass(monkeypatch) -> None:
    monkeypatch.setattr(loop, "activate_autonomous_candidate", lambda *a, **k: _Activation())
    monkeypatch.setattr(loop, "rollback_on_regression", lambda *a, **k: None)

    result = loop.run_self_harness_autopilot(
        events=_events("final_qa answer mismatch"),
        receipt_runner=_all_pass,
    )

    assert result["candidate_count"] >= 1
    assert len(result["activated"]) == 1
    assert result["activated"][0]["rollback_snapshot_id"] == "snap-old"
    assert not result["rolled_back"]
    assert not result["errors"]


def test_autopilot_rolls_back_on_post_activation_regression(monkeypatch) -> None:
    monkeypatch.setattr(loop, "activate_autonomous_candidate", lambda *a, **k: _Activation())
    monkeypatch.setattr(loop, "rollback_on_regression", lambda *a, **k: object())

    result = loop.run_self_harness_autopilot(
        events=_events("final_qa answer mismatch"),
        receipt_runner=_all_pass,
    )

    assert len(result["rolled_back"]) == 1
    assert result["rolled_back"][0]["reason"] == "post_activation_regression"
    assert not result["activated"]


def test_autopilot_holds_when_receipts_fail(monkeypatch) -> None:
    called = {"activated": False}

    def _should_not_run(*_a: object, **_k: object) -> object:
        called["activated"] = True
        raise AssertionError("must not activate on failed receipts")

    monkeypatch.setattr(loop, "activate_autonomous_candidate", _should_not_run)

    result = loop.run_self_harness_autopilot(
        events=_events("final_qa answer mismatch"),
        receipt_runner=_all_fail,
    )

    assert called["activated"] is False
    assert result["held"]
    assert not result["activated"]


def test_autopilot_skips_unsafe_candidate(monkeypatch) -> None:
    monkeypatch.setattr(loop, "activate_autonomous_candidate", lambda *a, **k: _Activation())
    monkeypatch.setattr(loop, "rollback_on_regression", lambda *a, **k: None)

    result = loop.run_self_harness_autopilot(
        events=_events("reviewer leak via ~/.ssh authorized_keys"),
        receipt_runner=_all_pass,
    )

    assert result["skipped_unsafe"]
    assert not result["activated"]


def test_autopilot_uses_llm_miner_and_proposer(monkeypatch) -> None:
    monkeypatch.setattr(loop, "activate_autonomous_candidate", lambda *a, **k: _Activation())
    monkeypatch.setattr(loop, "rollback_on_regression", lambda *a, **k: None)
    calls: list[str] = []

    def fake_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
        task = str(kwargs.get("task") or "")
        calls.append(task)
        messages = kwargs.get("messages")
        assert isinstance(messages, list)
        user_message = messages[1]
        assert isinstance(user_message, dict)
        typed_message = cast("dict[str, object]", user_message)
        user_payload = json.loads(str(typed_message.get("content") or ""))
        if task == loop.WEAKNESS_MINER_TASK:
            payload = json.dumps(user_payload["deterministic_bundle"])
        else:
            payload = json.dumps({"candidates": user_payload["deterministic_candidates"]})
        return {"content": f"```json\n{payload}\n```"}

    def extract(response: object) -> str:
        assert isinstance(response, dict)
        typed_response = cast("dict[str, object]", response)
        return str(typed_response.get("content") or "")

    result = loop.run_self_harness_autopilot(
        events=_events("final_qa answer mismatch"),
        receipt_runner=_all_pass,
        call_llm=fake_call_llm,
        extract_content=extract,
    )

    assert calls == [loop.WEAKNESS_MINER_TASK, loop.PROPOSER_TASK]
    assert len(result["activated"]) == 1


def test_register_self_harness_cron_is_idempotent(monkeypatch) -> None:
    created: list[dict[str, Any]] = []

    import cron.jobs as cron_jobs

    monkeypatch.setattr(cron_jobs, "list_jobs", lambda include_disabled=False: [])
    monkeypatch.setattr(
        cron_jobs,
        "create_job",
        lambda **kwargs: created.append(kwargs) or {"id": "job-1", **kwargs},
    )

    job = loop.register_self_harness_cron(script_path=loop._AUTOPILOT_SCRIPT_NAME)
    assert job is not None
    assert created[0]["name"] == loop.CRON_JOB_NAME
    assert created[0]["no_agent"] is True
    assert created[0]["script"] == loop._AUTOPILOT_SCRIPT_NAME

    monkeypatch.setattr(
        cron_jobs,
        "list_jobs",
        lambda include_disabled=False: [{"name": loop.CRON_JOB_NAME}],
    )
    assert loop.register_self_harness_cron(script_path=loop._AUTOPILOT_SCRIPT_NAME) is None


def test_install_autopilot_script_lands_in_miho_scripts_dir(tmp_path, monkeypatch) -> None:
    import importlib

    import miho_constants

    monkeypatch.setenv("MIHO_HOME", str(tmp_path / "miho_home"))
    importlib.reload(miho_constants)

    basename = loop._install_autopilot_script()

    # cron's path guard resolves (scripts_dir / basename) and requires it to be
    # under ~/.miho/scripts. Registering by basename must satisfy that.
    assert basename == loop._AUTOPILOT_SCRIPT_NAME
    scripts_dir = miho_constants.get_miho_home() / "scripts"
    installed = (scripts_dir / basename).resolve()
    installed.relative_to(scripts_dir.resolve())  # raises if guard would reject
    body = installed.read_text(encoding="utf-8")
    assert "run_self_harness_autopilot" in body
    assert "sys.path.insert" in body


def _candidate(failure: str) -> dict[str, Any]:
    from plugins.governance_os.self_harness import (
        build_evidence_bundle,
        build_shadow_candidates,
    )

    bundle = build_evidence_bundle(_events(failure))
    candidates = build_shadow_candidates(bundle)
    assert candidates, "expected at least one shadow candidate"
    return candidates[0]
