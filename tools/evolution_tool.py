"""Tool wrapper for Miho Evolution OS ledger/snapshots.

This exposes conservative self-harness operations to the agent.  It can record
and mine evolution signals, list/show ledger entries, create snapshots, and
rollback using the same curator backup safety engine used by the CLI.
"""

from __future__ import annotations

from tools.registry import registry, tool_error, tool_result


EVOLUTION_SCHEMA = {
    "name": "evolution",
    "description": (
        "Operate Miho Evolution OS: append-only ledger events, weakness mining "
        "from skill_curator candidates, skill-tree snapshots, and rollback via "
        "snapshot/event id. Use this for self-harness improvement tracking and "
        "reversible skill/harness evolution."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "list", "show", "record", "mine", "propose", "validate", "promote", "cycle", "train", "immunity", "doctor", "autopilot", "snapshot", "rollback"],
                "description": "Evolution action to perform.",
            },
            "kind": {
                "type": "string",
                "enum": ["proposal", "promotion", "rollback", "snapshot", "failure_pattern", "harness_rule", "note"],
                "description": "Event kind for record/list filtering.",
            },
            "title": {"type": "string", "description": "Event title for record."},
            "summary": {"type": "string", "description": "Short event summary."},
            "evidence": {"type": "string", "description": "Evidence or trace for the event."},
            "status": {"type": "string", "description": "Event status for record."},
            "event_id": {"type": "integer", "description": "Evolution event id for show/rollback."},
            "snapshot_id": {"type": "string", "description": "Raw snapshot id for rollback."},
            "reason": {"type": "string", "description": "Snapshot reason label."},
            "limit": {"type": "integer", "description": "Maximum rows/candidates."},
            "min_hits": {"type": "integer", "description": "Minimum repeated failure hits before proposing."},
            "auto_promote": {"type": "boolean", "description": "When true, cycle promotes validated low-risk proposals to active harness rules."},
            "max_cycles": {"type": "integer", "description": "Maximum autopilot cycles."},
            "target_score": {"type": "integer", "description": "Autopilot readiness target score, 1-100."},
        },
        "required": ["action"],
    },
}


def evolution_tool(args: dict) -> str:
    action = str(args.get("action") or "").strip()
    try:
        from agent import evolution as evo
        from agent import curator_backup
    except Exception as exc:
        return tool_error(f"Evolution OS unavailable: {exc}", success=False)

    try:
        if action == "status":
            return tool_result(
                success=True,
                ledger=str(evo.events_path()),
                events=len(evo.list_events(limit=None)),
                snapshots=len(curator_backup.list_backups()),
            )

        if action == "list":
            return tool_result(
                success=True,
                events=evo.list_events(
                    limit=int(args.get("limit") or 20),
                    kind=args.get("kind"),
                ),
            )

        if action == "show":
            event_id = args.get("event_id")
            if event_id is None:
                return tool_error("event_id is required for show", success=False)
            event = evo.get_event(int(event_id))
            if not event:
                return tool_error(f"evolution event {event_id} not found", success=False)
            return tool_result(success=True, event=event)

        if action == "record":
            event = evo.record_event(
                kind=str(args.get("kind") or "note"),
                title=str(args.get("title") or "Evolution note"),
                summary=str(args.get("summary") or ""),
                evidence=str(args.get("evidence") or ""),
                status=str(args.get("status") or "recorded"),
            )
            return tool_result(success=True, event=event)

        if action == "mine":
            return tool_result(evo.mine_skill_candidates(limit=int(args.get("limit") or 50)))

        if action == "propose":
            return tool_result(evo.generate_proposals(
                min_hits=int(args.get("min_hits") or 2),
                limit=int(args.get("limit") or 50),
            ))

        if action == "validate":
            event_id = args.get("event_id")
            if event_id is None:
                return tool_error("event_id is required for validate", success=False)
            return tool_result(evo.validate_proposal(int(event_id)))

        if action == "promote":
            event_id = args.get("event_id")
            if event_id is None:
                return tool_error("event_id is required for promote", success=False)
            return tool_result(evo.promote_proposal(int(event_id)))

        if action == "cycle":
            return tool_result(evo.run_evolution_cycle(
                min_hits=int(args.get("min_hits") or 2),
                mine_limit=int(args.get("limit") or 50),
                auto_promote=bool(args.get("auto_promote", False)),
            ))

        if action == "train":
            return tool_result(evo.run_training_ground(
                auto_promote=bool(args.get("auto_promote", True)),
            ))

        if action == "immunity":
            return tool_result(evo.run_immunity_check())

        if action == "doctor":
            return tool_result(evo.evolution_readiness_report())

        if action == "autopilot":
            return tool_result(evo.run_evolution_autopilot(
                max_cycles=int(args.get("max_cycles") or 5),
                target_score=int(args.get("target_score") or 100),
            ))

        if action == "snapshot":
            return tool_result(
                evo.snapshot_skills(reason=str(args.get("reason") or "manual-evolution-tool"))
            )

        if action == "rollback":
            event_id = args.get("event_id")
            snapshot_id = args.get("snapshot_id")
            if event_id is not None:
                ok, msg, data = evo.rollback_event(int(event_id))
                return tool_result(success=ok, message=msg, **(data or {}))
            if snapshot_id:
                ok, msg, safety = curator_backup.rollback(backup_id=str(snapshot_id))
                event = evo.record_event(
                    kind="rollback",
                    title=f"tool rollback snapshot {snapshot_id}",
                    summary=msg,
                    snapshot_id=str(snapshot_id),
                    status="rolled_back" if ok else "failed",
                    metadata={"safety_snapshot": str(safety) if safety else None},
                )
                return tool_result(
                    success=ok,
                    message=msg,
                    safety_snapshot=str(safety) if safety else None,
                    rollback_event=event,
                )
            return tool_error("event_id or snapshot_id is required for rollback", success=False)

        return tool_error("Unknown action. Use status, list, show, record, mine, propose, validate, promote, cycle, train, immunity, doctor, autopilot, snapshot, or rollback.", success=False)
    except ValueError as exc:
        return tool_error(str(exc), success=False)
    except Exception as exc:
        return tool_error(f"Evolution action failed: {exc}", success=False)


def check_evolution_requirements() -> bool:
    return True


registry.register(
    name="evolution",
    toolset="evolution",
    schema=EVOLUTION_SCHEMA,
    handler=lambda args, **kw: evolution_tool(args),
    check_fn=check_evolution_requirements,
    emoji="🧬",
)
