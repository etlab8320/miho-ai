"""Runtime learning bridge for owner profile and skill evolution."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def record_runtime_learning(
    *,
    request_id: str,
    playbook_key: str,
    failure_signature: str,
    user_feedback: str,
    artifact_paths: Iterable[str] = (),
    tools_used: Iterable[str] = (),
    autopilot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist Self-Harness learning to profile memory and skill candidates."""

    feedback = str(user_feedback or "").strip()
    playbook = str(playbook_key or "").strip()
    failure = str(failure_signature or "").strip()
    if not feedback or not playbook or not failure:
        return {"ready": False, "errors": ["missing_runtime_learning_inputs"]}

    profile_event = _try_append_owner_profile_event(
        request_id=request_id,
        playbook_key=playbook,
        failure_signature=failure,
        user_feedback=feedback,
        artifact_paths=tuple(str(item) for item in artifact_paths if str(item).strip()),
        tools_used=tuple(str(item) for item in tools_used if str(item).strip()),
        autopilot=autopilot or {},
    )
    skill_candidate = _try_record_skill_candidate(
        request_id=request_id,
        playbook_key=playbook,
        failure_signature=failure,
        user_feedback=feedback,
        artifact_paths=tuple(str(item) for item in artifact_paths if str(item).strip()),
        tools_used=tuple(str(item) for item in tools_used if str(item).strip()),
        autopilot=autopilot or {},
    )
    profile_job = _try_ensure_owner_profile_job()
    skill_job = _try_ensure_skill_review_job()
    evolution_import = _try_import_skill_candidates_to_evolution()
    results = {
        "owner_profile_event": profile_event,
        "skill_candidate": skill_candidate,
        "owner_profile_job": profile_job,
        "skill_review_job": skill_job,
        "evolution_import": evolution_import,
    }
    errors = [
        str(result.get("error"))
        for result in results.values()
        if isinstance(result, dict) and result.get("error")
    ]
    return {"ready": not errors, "errors": errors, **results}


def _try_append_owner_profile_event(
    *,
    request_id: str,
    playbook_key: str,
    failure_signature: str,
    user_feedback: str,
    artifact_paths: tuple[str, ...],
    tools_used: tuple[str, ...],
    autopilot: dict[str, Any],
) -> dict[str, Any]:
    try:
        from miho_cli.owner_profile import append_profile_event

        return append_profile_event(
            category="miho_self_harness",
            title=f"{playbook_key}: {failure_signature}",
            content=_learning_content(
                request_id=request_id,
                playbook_key=playbook_key,
                failure_signature=failure_signature,
                user_feedback=user_feedback,
                artifact_paths=artifact_paths,
                tools_used=tools_used,
                autopilot=autopilot,
            ),
            source="governance_os.self_harness_runtime",
        )
    except Exception as exc:
        return {"success": False, "error": f"owner_profile_update_failed: {exc}"}


def _try_record_skill_candidate(
    *,
    request_id: str,
    playbook_key: str,
    failure_signature: str,
    user_feedback: str,
    artifact_paths: tuple[str, ...],
    tools_used: tuple[str, ...],
    autopilot: dict[str, Any],
) -> dict[str, Any]:
    try:
        from miho_cli.skill_curator import record_skill_candidate

        return record_skill_candidate(
            kind="failure_pattern",
            title=f"Governance failure pattern: {playbook_key}/{failure_signature}",
            summary=(
                f"Repeated Self-Harness signal for {playbook_key}: "
                f"{failure_signature}. Review whether an existing skill should "
                "be patched or a reusable workflow should become a new skill."
            ),
            evidence=_learning_content(
                request_id=request_id,
                playbook_key=playbook_key,
                failure_signature=failure_signature,
                user_feedback=user_feedback,
                artifact_paths=artifact_paths,
                tools_used=tools_used,
                autopilot=autopilot,
            ),
            suggested_skill=_suggested_skill_name(playbook_key, failure_signature),
            source="governance_os.self_harness_runtime",
        )
    except Exception as exc:
        return {"success": False, "error": f"skill_candidate_update_failed: {exc}"}


def _try_ensure_owner_profile_job() -> dict[str, Any]:
    try:
        from miho_cli.owner_profile import ensure_daily_summary_job

        return ensure_daily_summary_job()
    except Exception as exc:
        return {"success": False, "error": f"owner_profile_job_failed: {exc}"}


def _try_ensure_skill_review_job() -> dict[str, Any]:
    try:
        from miho_cli.skill_curator import ensure_daily_skill_review_job

        return ensure_daily_skill_review_job()
    except Exception as exc:
        return {"success": False, "error": f"skill_review_job_failed: {exc}"}


def _try_import_skill_candidates_to_evolution() -> dict[str, Any]:
    try:
        from agent import evolution

        return evolution.mine_skill_candidates(limit=50)
    except Exception as exc:
        return {"success": False, "error": f"evolution_import_failed: {exc}"}


def _learning_content(
    *,
    request_id: str,
    playbook_key: str,
    failure_signature: str,
    user_feedback: str,
    artifact_paths: tuple[str, ...],
    tools_used: tuple[str, ...],
    autopilot: dict[str, Any],
) -> str:
    return "\n".join(
        (
            f"request_id: {request_id}",
            f"playbook_key: {playbook_key}",
            f"failure_signature: {failure_signature}",
            f"user_feedback: {user_feedback}",
            f"artifact_paths: {', '.join(artifact_paths) if artifact_paths else '-'}",
            f"tools_used: {', '.join(tools_used) if tools_used else '-'}",
            f"candidate_count: {len(autopilot.get('activated') or []) + len(autopilot.get('held') or []) + len(autopilot.get('rolled_back') or [])}",
            f"activated_count: {len(autopilot.get('activated') or [])}",
            f"rolled_back_count: {len(autopilot.get('rolled_back') or [])}",
        )
    )


def _suggested_skill_name(playbook_key: str, failure_signature: str) -> str:
    raw = f"miho-{playbook_key}-{failure_signature}".casefold()
    chars = [char if char.isalnum() else "-" for char in raw]
    return "-".join("".join(chars).split("-"))[:80]
