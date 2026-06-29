"""CLI subcommand: `miho evolution <subcommand>`.

Auditable, reversible evolution commands for Miho's skill/harness layer.  This
is intentionally conservative: it records ledger entries and calls the existing
curator backup/rollback engine rather than inventing a second restore path.
"""

from __future__ import annotations

import argparse
import json
import sys


def _cmd_status(args) -> int:
    from agent import evolution
    from agent import curator_backup

    print("evolution: ENABLED")
    print(f"  ledger:    {evolution.events_path()}")
    print(f"  events:    {len(evolution.list_events(limit=None))}")
    print(f"  snapshots: {len(curator_backup.list_backups())}")
    return 0


def _cmd_list(args) -> int:
    from agent import evolution

    limit = int(getattr(args, "limit", 20) or 20)
    kind = getattr(args, "kind", None)
    print(evolution.summarize_events(limit=limit) if not kind else _summarize_kind(kind, limit))
    return 0


def _summarize_kind(kind: str, limit: int) -> str:
    from agent import evolution

    rows = evolution.list_events(limit=limit, kind=kind)
    if not rows:
        return f"No evolution events for kind={kind}."
    return "\n".join(
        f"#{e.get('id')} {e.get('created_at')} {e.get('status')} "
        f"snapshot={e.get('snapshot_id') or '-'} - {e.get('title')}"
        for e in rows
    )


def _cmd_show(args) -> int:
    from agent import evolution

    event = evolution.get_event(int(args.event_id))
    if not event:
        print(f"evolution: event {args.event_id} not found", file=sys.stderr)
        return 1
    print(json.dumps(event, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _cmd_snapshot(args) -> int:
    from agent import evolution

    reason = getattr(args, "reason", None) or "manual-evolution-snapshot"
    result = evolution.snapshot_skills(reason=reason)
    if not result.get("success"):
        print(f"evolution: snapshot failed - {result.get('error')}", file=sys.stderr)
        return 1
    print(f"evolution: snapshot {result['snapshot_id']} created")
    print(f"  event: #{result['event']['id']}")
    print(f"  path:  {result['path']}")
    return 0


def _cmd_rollback(args) -> int:
    from agent import evolution
    from agent import curator_backup

    if getattr(args, "list", False):
        print(curator_backup.summarize_backups())
        return 0

    event_id = getattr(args, "event_id", None)
    snapshot_id = getattr(args, "snapshot_id", None)
    if event_id is None and not snapshot_id:
        print("evolution: provide EVENT_ID or --snapshot-id, or use --list", file=sys.stderr)
        return 2

    if event_id is not None:
        event = evolution.get_event(int(event_id))
        if not event:
            print(f"evolution: event {event_id} not found", file=sys.stderr)
            return 1
        target = event.get("snapshot_id")
        print(f"Rollback target: event #{event_id} snapshot={target}")
        if not target:
            print("evolution: that event has no snapshot_id", file=sys.stderr)
            return 1
        if not getattr(args, "yes", False):
            ans = input("Proceed? [y/N] ").strip().lower()
            if ans not in {"y", "yes"}:
                print("cancelled")
                return 1
        ok, msg, data = evolution.rollback_event(int(event_id))
        print(f"evolution: {msg}")
        if data.get("rollback_event"):
            print(f"  rollback event: #{data['rollback_event']['id']}")
        return 0 if ok else 1

    print(f"Rollback target: snapshot {snapshot_id}")
    if not getattr(args, "yes", False):
        ans = input("Proceed? [y/N] ").strip().lower()
        if ans not in {"y", "yes"}:
            print("cancelled")
            return 1
    ok, msg, safety = curator_backup.rollback(backup_id=snapshot_id)
    event = evolution.record_event(
        kind="rollback",
        title=f"rollback snapshot {snapshot_id}",
        summary=msg,
        snapshot_id=snapshot_id,
        status="rolled_back" if ok else "failed",
        metadata={"safety_snapshot": str(safety) if safety else None},
    )
    print(f"evolution: {msg}")
    print(f"  rollback event: #{event['id']}")
    return 0 if ok else 1


def _cmd_record(args) -> int:
    from agent import evolution

    event = evolution.record_event(
        kind=args.kind,
        title=args.title,
        summary=args.summary or "",
        evidence=args.evidence or "",
        status=args.status or "recorded",
    )
    print(f"evolution: recorded #{event['id']} {event['kind']} - {event['title']}")
    return 0


def _cmd_mine(args) -> int:
    from agent import evolution

    result = evolution.mine_skill_candidates(limit=int(getattr(args, "limit", 50) or 50))
    if not result.get("success"):
        print(f"evolution: mining failed - {result.get('error')}", file=sys.stderr)
        return 1
    print(
        f"evolution: mined {len(result.get('created') or [])} event(s), "
        f"skipped {len(result.get('skipped') or [])}, checked {result.get('checked', 0)}"
    )
    for event in result.get("created") or []:
        print(f"  #{event.get('id')} {event.get('kind')} - {event.get('title')}")
    return 0


def _cmd_propose(args) -> int:
    from agent import evolution

    result = evolution.generate_proposals(
        min_hits=int(getattr(args, "min_hits", 2) or 2),
        limit=int(getattr(args, "limit", 50) or 50),
    )
    print(
        f"evolution: proposed {len(result.get('created') or [])} event(s), "
        f"skipped {len(result.get('skipped') or [])}, clusters {result.get('clusters', 0)}"
    )
    for event in result.get("created") or []:
        print(f"  #{event.get('id')} - {event.get('title')}")
    return 0 if result.get("success") else 1


def _cmd_validate(args) -> int:
    from agent import evolution

    result = evolution.validate_proposal(int(args.event_id))
    if not result.get("success"):
        print(f"evolution: validation failed - {result.get('error')}", file=sys.stderr)
        return 1
    print(f"evolution: validated #{args.event_id} as event #{result['event']['id']}")
    return 0


def _cmd_promote(args) -> int:
    from agent import evolution

    result = evolution.promote_proposal(int(args.event_id))
    if not result.get("success"):
        print(f"evolution: promotion failed - {result.get('error')}", file=sys.stderr)
        return 1
    event = result.get("event") or {}
    if result.get("already_active"):
        print(f"evolution: proposal #{args.event_id} already active")
    else:
        print(f"evolution: promoted #{args.event_id} to harness rule event #{event.get('id')}")
    return 0


def _cmd_cycle(args) -> int:
    from agent import evolution

    result = evolution.run_evolution_cycle(
        min_hits=int(getattr(args, "min_hits", 2) or 2),
        mine_limit=int(getattr(args, "limit", 50) or 50),
        auto_promote=bool(getattr(args, "auto_promote", False)),
    )
    print(
        f"evolution: cycle mined={len(result.get('mined', {}).get('created') or [])} "
        f"proposed={len(result.get('proposals', {}).get('created') or [])} "
        f"validated={len(result.get('validated') or [])} "
        f"promoted={len(result.get('promoted') or [])} "
        f"active_rules={len(result.get('active_rules') or [])}"
    )
    return 0 if result.get("success") else 1


def _cmd_train(args) -> int:
    from agent import evolution

    result = evolution.run_training_ground(auto_promote=bool(getattr(args, "auto_promote", False)))
    print(
        f"evolution: training failures={result.get('training_failures', 0)} "
        f"proposed={len(result.get('proposals', {}).get('created') or [])} "
        f"validated={len(result.get('validated') or [])} "
        f"promoted={len(result.get('promoted') or [])} "
        f"active_rules={len(result.get('active_rules') or [])}"
    )
    return 0 if result.get("success") else 1


def _cmd_immunity(args) -> int:
    from agent import evolution

    result = evolution.run_immunity_check()
    print(f"evolution: immunity {'passed' if result.get('passed') else 'failed'}")
    for name, check in (result.get("checks") or {}).items():
        print(f"  {name}: {'PASS' if check.get('passed') else 'FAIL'} {check.get('detail') or ''}".rstrip())
    return 0 if result.get("passed") else 1


def _cmd_doctor(args) -> int:
    from agent import evolution

    report = evolution.evolution_readiness_report()
    print(f"evolution: readiness {report.get('score')}% - {report.get('level')}")
    for name, ok in (report.get("checks") or {}).items():
        print(f"  {name}: {'PASS' if ok else 'MISSING'}")
    if report.get("missing"):
        print("  missing: " + ", ".join(report["missing"]))
    return 0 if int(report.get("score") or 0) == 100 else 1


def _cmd_autopilot(args) -> int:
    from agent import evolution

    result = evolution.run_evolution_autopilot(
        max_cycles=int(getattr(args, "max_cycles", 5) or 5),
        target_score=int(getattr(args, "target_score", 100) or 100),
    )
    readiness = result.get("readiness") or {}
    print(
        f"evolution: autopilot cycles={result.get('cycles')} "
        f"target_reached={bool(result.get('target_reached'))} "
        f"readiness={readiness.get('score')}% level={readiness.get('level')}"
    )
    if readiness.get("missing"):
        print("  missing: " + ", ".join(readiness["missing"]))
    return 0 if result.get("target_reached") else 1


def _cmd_wikigraph(args) -> int:
    import importlib

    system_wikigraph = importlib.import_module("agent.system_wikigraph")

    action = getattr(args, "wikigraph_action", None)
    if action == "init":
        result = system_wikigraph.init_wiki()
        print("wikigraph: initialized")
        print(f"  wiki:  {result['wiki_dir']}")
        print(f"  graph: {result['db_path']}")
        if result.get("created"):
            print(f"  created: {len(result['created'])} file(s)")
        return 0
    if action == "sync":
        result = system_wikigraph.sync_project(
            project_root=getattr(args, "project_root", None),
            full=bool(getattr(args, "full", False)),
            from_git=bool(getattr(args, "from_git", False)),
        )
        summary = result.get("summary") or {}
        print(f"wikigraph: synced #{result.get('sync_id')} project={result.get('project_root')}")
        print(
            "  "
            + ", ".join(
                f"{key}={summary.get(key, 0)}"
                for key in ("files", "tests", "tools", "skills", "configs", "events", "edges")
            )
        )
        if result.get("changed_files"):
            print(f"  changed_files: {len(result['changed_files'])}")
        print(f"  wiki:  {result['wiki_dir']}")
        print(f"  graph: {result['db_path']}")
        return 0
    if action == "status":
        print(system_wikigraph.status_text(system_wikigraph.graph_status()))
        return 0
    if action == "impact":
        print(system_wikigraph.render_impact_text(system_wikigraph.impact(args.query, limit=args.limit)))
        return 0
    if action == "query":
        print(system_wikigraph.render_graphrag_text(system_wikigraph.graphrag(args.query, hops=args.hops, limit=args.limit)))
        return 0
    if action == "visualize":
        result = system_wikigraph.render_graph_html(args.query, output_path=getattr(args, "output", None), limit=args.limit)
        print("wikigraph: visualized")
        print(f"  output: {result['output_path']}")
        print(f"  nodes={result['nodes']} edges={result['edges']} wiki_hits={result['wiki_hits']}")
        return 0
    if action == "install-hooks":
        result = system_wikigraph.install_git_hooks(project_root=getattr(args, "project_root", None), force=bool(getattr(args, "force", False)))
        print("wikigraph: git hooks installed")
        print(f"  repo: {result['repo']}")
        print(f"  installed: {len(result['installed'])}")
        if result.get("skipped"):
            print(f"  skipped_existing_non_miho_hooks: {len(result['skipped'])}")
        print(f"  log: {result['log_path']}")
        return 0
    if action == "watch-once":
        result = system_wikigraph.watch_once(project_root=getattr(args, "project_root", None))
        print(f"wikigraph: watch-once sync #{result.get('sync_id')} changed_files={len(result.get('changed_files') or [])}")
        return 0
    print("evolution wikigraph: choose init, sync, status, impact, query, visualize, install-hooks, or watch-once", file=sys.stderr)
    return 2


def register_cli(parent: argparse.ArgumentParser) -> None:
    parent.set_defaults(func=lambda a: (parent.print_help(), 0)[1])
    subs = parent.add_subparsers(dest="evolution_command")

    p_status = subs.add_parser("status", help="Show evolution ledger/snapshot status")
    p_status.set_defaults(func=_cmd_status)

    p_list = subs.add_parser("list", aliases=["ls"], help="List evolution events")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--kind", default=None)
    p_list.set_defaults(func=_cmd_list)

    p_show = subs.add_parser("show", help="Show one evolution event as JSON")
    p_show.add_argument("event_id", type=int)
    p_show.set_defaults(func=_cmd_show)

    p_snapshot = subs.add_parser("snapshot", help="Take a reversible skill-tree snapshot")
    p_snapshot.add_argument("--reason", default=None)
    p_snapshot.set_defaults(func=_cmd_snapshot)

    p_rollback = subs.add_parser("rollback", help="Rollback using an evolution event or snapshot")
    p_rollback.add_argument("event_id", type=int, nargs="?", help="Evolution event id with snapshot_id")
    p_rollback.add_argument("--snapshot-id", default=None, help="Raw curator/evolution snapshot id")
    p_rollback.add_argument("--list", action="store_true", help="List available skill snapshots")
    p_rollback.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    p_rollback.set_defaults(func=_cmd_rollback)

    p_record = subs.add_parser("record", help="Manually append an evolution event")
    p_record.add_argument("kind", choices=sorted(__import__("agent.evolution", fromlist=["VALID_EVENT_KINDS"]).VALID_EVENT_KINDS))
    p_record.add_argument("title")
    p_record.add_argument("--summary", default="")
    p_record.add_argument("--evidence", default="")
    p_record.add_argument("--status", default="recorded")
    p_record.set_defaults(func=_cmd_record)

    p_mine = subs.add_parser("mine", help="Import pending skill_curator candidates into the evolution ledger")
    p_mine.add_argument("--limit", type=int, default=50)
    p_mine.set_defaults(func=_cmd_mine)

    p_propose = subs.add_parser("propose", help="Generate harness proposals from repeated failure patterns")
    p_propose.add_argument("--min-hits", type=int, default=2)
    p_propose.add_argument("--limit", type=int, default=50)
    p_propose.set_defaults(func=_cmd_propose)

    p_validate = subs.add_parser("validate", help="Validate a proposal before promotion")
    p_validate.add_argument("event_id", type=int)
    p_validate.set_defaults(func=_cmd_validate)

    p_promote = subs.add_parser("promote", help="Promote a validated proposal to an active harness rule")
    p_promote.add_argument("event_id", type=int)
    p_promote.set_defaults(func=_cmd_promote)

    p_cycle = subs.add_parser("cycle", help="Run one mine/propose/validate cycle")
    p_cycle.add_argument("--min-hits", type=int, default=2)
    p_cycle.add_argument("--limit", type=int, default=50)
    p_cycle.add_argument("--auto-promote", action="store_true", help="Promote validated low-risk proposals to active harness rules")
    p_cycle.set_defaults(func=_cmd_cycle)

    p_train = subs.add_parser("train", help="Run deterministic Evolution training-ground drills")
    p_train.add_argument("--auto-promote", action="store_true", help="Promote validated drill proposals to active harness rules")
    p_train.set_defaults(func=_cmd_train)

    p_immunity = subs.add_parser("immunity", help="Run Evolution immunity/safety drills")
    p_immunity.set_defaults(func=_cmd_immunity)

    p_doctor = subs.add_parser("doctor", help="Score Evolution readiness gates")
    p_doctor.set_defaults(func=_cmd_doctor)

    p_autopilot = subs.add_parser("autopilot", help="Loop training, immunity, and readiness until target score")
    p_autopilot.add_argument("--max-cycles", type=int, default=5)
    p_autopilot.add_argument("--target-score", type=int, default=100)
    p_autopilot.set_defaults(func=_cmd_autopilot)

    p_wikigraph = subs.add_parser("wikigraph", aliases=["wg"], help="Build and query the local Miho System WikiGraph")
    wg_sub = p_wikigraph.add_subparsers(dest="wikigraph_action")

    wg_init = wg_sub.add_parser("init", help="Create ~/.miho/system_wiki and ~/.miho/system_graph")
    wg_init.set_defaults(func=_cmd_wikigraph)

    wg_sync = wg_sub.add_parser("sync", help="Index Miho source/runtime structure into the WikiGraph")
    wg_sync.add_argument("--project-root", default=None, help="Project root to scan; defaults to current directory")
    wg_sync.add_argument("--full", action="store_true", help="Scan the full project even when --from-git is used")
    wg_sync.add_argument("--from-git", action="store_true", help="Use git status changed files as the primary sync input")
    wg_sync.set_defaults(func=_cmd_wikigraph)

    wg_status = wg_sub.add_parser("status", help="Show WikiGraph node/edge counts and last sync")
    wg_status.set_defaults(func=_cmd_wikigraph)

    wg_impact = wg_sub.add_parser("impact", help="Show related nodes/edges for a file, component, tool, or phrase")
    wg_impact.add_argument("query")
    wg_impact.add_argument("--limit", type=int, default=40)
    wg_impact.set_defaults(func=_cmd_wikigraph)

    wg_query = wg_sub.add_parser("query", help="GraphRAG query: expand related nodes, risks, wiki pages, and tests")
    wg_query.add_argument("query")
    wg_query.add_argument("--hops", type=int, default=2)
    wg_query.add_argument("--limit", type=int, default=80)
    wg_query.set_defaults(func=_cmd_wikigraph)

    wg_visualize = wg_sub.add_parser("visualize", aliases=["viz"], help="Render a self-contained HTML/SVG WikiGraph map")
    wg_visualize.add_argument("query")
    wg_visualize.add_argument("--output", default=None)
    wg_visualize.add_argument("--limit", type=int, default=90)
    wg_visualize.set_defaults(func=_cmd_wikigraph)

    wg_hooks = wg_sub.add_parser("install-hooks", help="Install local git hooks that auto-sync WikiGraph after external edits")
    wg_hooks.add_argument("--project-root", default=None)
    wg_hooks.add_argument("--force", action="store_true", help="Overwrite existing Miho-managed hooks; skip non-Miho hooks unless set")
    wg_hooks.set_defaults(func=_cmd_wikigraph)

    wg_watch = wg_sub.add_parser("watch-once", help="Run one change-aware sync pass for cron/watchdog integration")
    wg_watch.add_argument("--project-root", default=None)
    wg_watch.set_defaults(func=_cmd_wikigraph)


def cli_main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="miho evolution")
    register_cli(parser)
    args = parser.parse_args(argv)
    fn = getattr(args, "func", None)
    if fn is None:
        parser.print_help()
        return 0
    return int(fn(args) or 0)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli_main())
