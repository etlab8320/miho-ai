"""Autonomous readiness probes for Governance OS repair loops."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import cast


def final_delivery_repair_probe_passed() -> bool:
    from .final_delivery_repair import repair_artifact_delivery

    with tempfile.TemporaryDirectory(prefix="miho-governance-delivery-") as tmp:
        root = Path(tmp)
        source = root / "workspace" / "probe.mhtml"
        source.parent.mkdir()
        source.write_text("probe", encoding="utf-8")
        staging = root / "allowed-media"
        old_allow = os.environ.get("MIHO_MEDIA_ALLOW_DIRS")
        os.environ["MIHO_MEDIA_ALLOW_DIRS"] = str(staging)
        try:
            result = repair_artifact_delivery(str(source), staging_dir=staging)
        finally:
            if old_allow is None:
                os.environ.pop("MIHO_MEDIA_ALLOW_DIRS", None)
            else:
                os.environ["MIHO_MEDIA_ALLOW_DIRS"] = old_allow
        return (
            result.status == "repaired"
            and bool(result.staged_path)
            and result.media_tag == f"MEDIA:`{result.staged_path}`"
            and Path(result.staged_path).is_file()
            and result.reviewer.get("status") == "pass"
        )


def final_qa_repair_probe_passed() -> bool:
    from .final_qa import FINAL_QA_REPAIR_TASK, FINAL_QA_TASK, repair_answer_until_pass

    calls: list[dict[str, object]] = []

    def fake_call_llm(**kwargs: object) -> object:
        calls.append(kwargs)
        if kwargs.get("task") == FINAL_QA_TASK:
            return "pass"
        return "수정된 최종 답변입니다."

    repaired = repair_answer_until_pass(
        "질문",
        "내부 검증 문구",
        evidence={"reason": "readiness"},
        call_llm=fake_call_llm,
        extract_content=lambda value: str(value),
    )
    return (
        repaired == "수정된 최종 답변입니다."
        and len(calls) == 2
        and calls[0].get("task") == FINAL_QA_REPAIR_TASK
        and calls[1].get("task") == FINAL_QA_TASK
    )


def self_harness_autonomy_probe_passed() -> bool:
    from miho_constants import reset_miho_home_override, set_miho_home_override

    from .self_harness import build_evidence_bundle, build_shadow_candidates
    from .self_harness_autonomy import activate_autonomous_candidate, rollback_on_regression
    from .versioning import load_runtime_registry

    with tempfile.TemporaryDirectory(prefix="miho-governance-self-harness-") as tmp:
        token = set_miho_home_override(Path(tmp) / ".miho")
        try:
            bundle = build_evidence_bundle(
                [
                    _promotion_probe_event(1, "discord_attachment_delivery", "attachment_delivery_failed"),
                    _promotion_probe_event(2, "discord_attachment_delivery", "attachment_delivery_failed"),
                ],
                min_recurrence=2,
            )
            [candidate] = build_shadow_candidates(bundle)
            activation = activate_autonomous_candidate(
                candidate,
                test_receipts=_passing_receipts(candidate),
            )
            activated = "final_delivery_repair" in load_runtime_registry().get_playbook(
                "discord_attachment_delivery"
            ).review_gates
            rollback = rollback_on_regression(
                activation,
                regression_receipts=(
                    {
                        "name": "tests/e2e/test_discord_governance_delivery.py",
                        "status": "failed",
                        "exit_code": 1,
                        "command": "pytest tests/e2e/test_discord_governance_delivery.py",
                        "evidence": "readiness regression",
                    },
                ),
            )
            rolled_back = "final_delivery_repair" not in load_runtime_registry().get_playbook(
                "discord_attachment_delivery"
            ).review_gates
            return activated and rollback is not None and rolled_back
        except Exception:
            return False
        finally:
            reset_miho_home_override(token)


def self_harness_runtime_feedback_probe_passed() -> bool:
    from miho_constants import reset_miho_home_override, set_miho_home_override

    from .self_harness_loop import PROPOSER_TASK, WEAKNESS_MINER_TASK
    from .self_harness_runtime import run_feedback_improvement_loop

    with tempfile.TemporaryDirectory(prefix="miho-governance-runtime-feedback-") as tmp:
        token = set_miho_home_override(Path(tmp) / ".miho")
        try:
            calls: list[str] = []

            def fake_call_llm(*_args: object, **kwargs: object) -> dict[str, object]:
                calls.append(str(kwargs.get("task") or ""))
                return _agentic_self_harness_payload(kwargs)

            result = run_feedback_improvement_loop(
                request_id="readiness-runtime-feedback",
                playbook_key="designed_pdf_artifact",
                failure_signature="pdf_footer_overflow",
                user_feedback="PDF footer overflow during readiness probe",
                artifact_paths=("/tmp/probe.pdf",),
                recent_events=(
                    _feedback_probe_event(
                        1,
                        "designed_pdf_artifact",
                        "pdf_footer_overflow",
                    ),
                ),
                receipt_runner=lambda _target: (0, "passed"),
                smoke_runner=lambda _target: (0, "passed"),
                call_llm=fake_call_llm,
                extract_content=_extract_content,
                record_failure=_probe_record_quality_failure,
            )
            learning = result.get("runtime_learning")
            return (
                result["status"] == "activated"
                and result["self_harness_triggered"] is True
                and result["user_visible_message_allowed"] is False
                and bool(result["recorded_event_id"])
                and isinstance(learning, dict)
                and learning.get("ready") is True
                and calls == [WEAKNESS_MINER_TASK, PROPOSER_TASK]
            )
        except Exception:
            return False
        finally:
            reset_miho_home_override(token)


def _passing_receipts(candidate: dict[str, object]) -> tuple[dict[str, object], ...]:
    validation = candidate.get("validation")
    typed_validation = cast("dict[str, object]", validation) if isinstance(validation, dict) else {}
    tests = typed_validation.get("required_tests", ())
    if not isinstance(tests, list | tuple):
        return ()
    receipts: list[dict[str, object]] = []
    for test_name in tests:
        receipts.append(
            {
                "name": str(test_name),
                "status": "passed",
                "exit_code": 0,
                "command": f"pytest {test_name}",
                "evidence": f"{test_name} passed",
            }
        )
    return tuple(receipts)


def _promotion_probe_event(event_id: int, playbook_key: str, failure: str) -> dict[str, object]:
    return {
        "id": event_id,
        "metadata": {
            "governance_outcome": {
                "request_id": f"readiness-self-harness-{event_id}",
                "playbook_key": playbook_key,
                "review_status": "fail",
                "failures": [failure],
            }
        },
    }


def _feedback_probe_event(event_id: int, playbook_key: str, failure: str) -> dict[str, object]:
    return {
        "id": event_id,
        "metadata": {
            "governance_outcome": {
                "request_id": f"readiness-feedback-{event_id}",
                "playbook_key": playbook_key,
                "review_status": "user_reported_failure",
                "failures": [failure],
                "artifact_paths": ["/tmp/probe.pdf"],
                "user_feedback": "PDF footer overflow",
            }
        },
    }


def _agentic_self_harness_payload(kwargs: object) -> dict[str, object]:
    import json

    typed = kwargs if isinstance(kwargs, dict) else {}
    messages = typed.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        return {"content": "{}"}
    user_message = messages[1]
    if not isinstance(user_message, dict):
        return {"content": "{}"}
    payload = json.loads(str(user_message.get("content") or "{}"))
    if typed.get("task") == "miho_self_harness_weakness_miner":
        content = payload.get("deterministic_bundle", {})
    else:
        content = {"candidates": payload.get("deterministic_candidates", [])}
    return {"content": json.dumps(content, ensure_ascii=False)}


def _extract_content(response: object) -> str:
    if isinstance(response, dict):
        return str(response.get("content") or "")
    return str(response or "")


def _probe_record_quality_failure(**kwargs: object) -> dict[str, object]:
    from .feedback_events import build_quality_failure_entry

    entry = build_quality_failure_entry(
        request_id=str(kwargs.get("request_id") or "readiness-runtime-feedback"),
        playbook_key=str(kwargs.get("playbook_key") or "designed_pdf_artifact"),
        failure_signature=str(kwargs.get("failure_signature") or "readiness_probe"),
        user_feedback=str(kwargs.get("user_feedback") or "readiness probe"),
        artifact_paths=tuple(str(item) for item in kwargs.get("artifact_paths") or ()),
        tools_used=tuple(str(item) for item in kwargs.get("tools_used") or ()),
    )
    return {
        "id": 1,
        "metadata": {"governance_outcome": entry.to_metadata()},
    }
