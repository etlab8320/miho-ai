"""Tool for recording and reviewing Miho skill evolution candidates."""

from __future__ import annotations

from miho_cli.skill_curator import (
    ensure_daily_skill_review_job,
    list_skill_candidates,
    record_skill_candidate,
    update_skill_candidate,
)
from tools.registry import registry, tool_error, tool_result


SKILL_CURATOR_SCHEMA = {
    "name": "skill_curator",
    "description": (
        "Record and review signals that Miho's skills should evolve. Use this "
        "proactively after failed attempts, repeated retries, missing tool steps, "
        "bad skill outcomes, or reusable workflows. It stores candidates only; "
        "use skill_view and skill_manage to actually patch/create skills after "
        "review. kind='failure_pattern' captures lessons from failure, "
        "kind='update_existing' proposes a patch to a known skill, and "
        "kind='new_skill' proposes a new official workflow skill."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "record_candidate",
                    "list_candidates",
                    "mark_promoted",
                    "dismiss_candidate",
                    "ensure_daily_review",
                ],
                "description": "Skill curator action to perform.",
            },
            "kind": {
                "type": "string",
                "enum": ["new_skill", "update_existing", "failure_pattern"],
                "description": "Candidate type for record/list operations.",
            },
            "title": {
                "type": "string",
                "description": "Short candidate title.",
            },
            "summary": {
                "type": "string",
                "description": "Concise reusable lesson or proposed skill change.",
            },
            "evidence": {
                "type": "string",
                "description": "Concrete failure, repeated workflow, or missing-step evidence.",
            },
            "suggested_skill": {
                "type": "string",
                "description": "Proposed new skill name for kind='new_skill'.",
            },
            "target_skill": {
                "type": "string",
                "description": "Existing skill to patch for kind='update_existing'.",
            },
            "source": {
                "type": "string",
                "description": "Source label such as discord, cli, cron, or manual.",
            },
            "status": {
                "type": "string",
                "enum": ["pending", "promoted", "dismissed"],
                "description": "Candidate status for list_candidates.",
            },
            "candidate_id": {
                "type": "integer",
                "description": "Candidate ID for mark_promoted or dismiss_candidate.",
            },
            "note": {
                "type": "string",
                "description": "Short promotion/dismissal note.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum rows for list_candidates.",
            },
            "schedule": {
                "type": "string",
                "description": "Cron expression for ensure_daily_review. Defaults to 10 23 * * *.",
            },
        },
        "required": ["action"],
    },
}


def skill_curator_tool(args: dict) -> str:
    action = str(args.get("action") or "").strip()

    if action == "record_candidate":
        try:
            result = record_skill_candidate(
                kind=str(args.get("kind") or ""),
                title=str(args.get("title") or ""),
                summary=str(args.get("summary") or ""),
                evidence=str(args.get("evidence") or ""),
                suggested_skill=args.get("suggested_skill"),
                target_skill=args.get("target_skill"),
                source=str(args.get("source") or "skill_curator"),
            )
        except ValueError as exc:
            return tool_error(str(exc), success=False)
        return tool_result(result)

    if action == "list_candidates":
        try:
            candidates = list_skill_candidates(
                status=str(args.get("status") or "pending"),
                kind=args.get("kind"),
                limit=int(args.get("limit") or 20),
            )
        except ValueError as exc:
            return tool_error(str(exc), success=False)
        return tool_result(success=True, candidates=candidates)

    if action == "mark_promoted":
        candidate_id = args.get("candidate_id")
        if candidate_id is None:
            return tool_error("candidate_id is required for mark_promoted", success=False)
        return tool_result(
            update_skill_candidate(
                int(candidate_id),
                status="promoted",
                note=args.get("note"),
            )
        )

    if action == "dismiss_candidate":
        candidate_id = args.get("candidate_id")
        if candidate_id is None:
            return tool_error("candidate_id is required for dismiss_candidate", success=False)
        return tool_result(
            update_skill_candidate(
                int(candidate_id),
                status="dismissed",
                note=args.get("note"),
            )
        )

    if action == "ensure_daily_review":
        return tool_result(
            ensure_daily_skill_review_job(
                schedule=str(args.get("schedule") or "10 23 * * *")
            )
        )

    return tool_error(
        "Unknown action. Use record_candidate, list_candidates, mark_promoted, "
        "dismiss_candidate, or ensure_daily_review.",
        success=False,
    )


def check_skill_curator_requirements() -> bool:
    return True


registry.register(
    name="skill_curator",
    toolset="skill_curator",
    schema=SKILL_CURATOR_SCHEMA,
    handler=lambda args, **kw: skill_curator_tool(args),
    check_fn=check_skill_curator_requirements,
    emoji="🧭",
)
