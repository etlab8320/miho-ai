"""Proposal mining and harness-rule promotion for Miho Evolution OS."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .evolution_ledger import (
    _now_iso,
    _write_harness_rules,
    get_event,
    list_events,
    list_harness_rules,
    record_event,
)


def mine_skill_candidates(*, limit: int = 50) -> Dict[str, Any]:
    """Import pending skill_curator candidates into the evolution ledger."""
    try:
        from miho_cli.skill_curator import list_skill_candidates
    except Exception as exc:
        return {"success": False, "error": f"skill_curator unavailable: {exc}"}

    candidates = list_skill_candidates(status="pending", limit=limit)
    existing_candidate_ids = {
        ((e.get("metadata") or {}).get("skill_candidate_id"))
        for e in list_events(limit=None)
    }
    created = []
    skipped = []
    for cand in candidates:
        candidate_id = cand.get("id")
        if candidate_id in existing_candidate_ids:
            skipped.append(candidate_id)
            continue
        kind = "failure_pattern" if cand.get("kind") == "failure_pattern" else "proposal"
        event = record_event(
            kind=kind,
            title=str(cand.get("title") or "skill curator candidate"),
            summary=str(cand.get("summary") or ""),
            evidence=str(cand.get("evidence") or ""),
            status="mined",
            metadata={
                "skill_candidate_id": candidate_id,
                "skill_candidate_kind": cand.get("kind"),
                "suggested_skill": cand.get("suggested_skill"),
                "target_skill": cand.get("target_skill"),
                "hits": cand.get("hits"),
            },
        )
        created.append(event)
    return {"success": True, "created": created, "skipped": skipped, "checked": len(candidates)}


def _proposal_signature(source_event_ids: Iterable[int]) -> str:
    return ",".join(str(int(x)) for x in sorted(source_event_ids))


def _existing_proposal_signatures() -> set[str]:
    signatures: set[str] = set()
    for event in list_events(limit=None, kind="proposal"):
        meta = event.get("metadata") or {}
        ids = meta.get("source_event_ids") or []
        if ids:
            signatures.add(_proposal_signature(ids))
    return signatures


def generate_proposals(*, min_hits: int = 2, limit: int = 50) -> Dict[str, Any]:
    """Cluster repeated failure patterns and create minimal harness proposals."""
    min_hits = max(1, int(min_hits or 1))
    failures = [
        e for e in list_events(limit=None, kind="failure_pattern")
        if (e.get("status") or "") in {"recorded", "mined", "failed", ""}
    ]
    clusters: Dict[str, List[Dict[str, Any]]] = {}
    for event in failures:
        title = str(event.get("title") or "").strip()
        if not title:
            continue
        clusters.setdefault(title.casefold(), []).append(event)

    existing = _existing_proposal_signatures()
    created: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for _key, events in sorted(clusters.items(), key=lambda item: item[0])[:limit]:
        if len(events) < min_hits:
            continue
        ordered = sorted(events, key=lambda e: int(e.get("id") or 0))
        source_ids = [int(e.get("id") or 0) for e in ordered]
        signature = _proposal_signature(source_ids)
        if signature in existing:
            skipped.append({"source_event_ids": source_ids, "reason": "proposal already exists"})
            continue
        title = str(ordered[0].get("title") or "Repeated failure")
        summary_parts = [str(e.get("summary") or "").strip() for e in ordered if str(e.get("summary") or "").strip()]
        evidence_parts = [str(e.get("evidence") or "").strip() for e in ordered if str(e.get("evidence") or "").strip()]
        summary = summary_parts[0] if summary_parts else f"Repeated failure pattern: {title}"
        proposal = record_event(
            kind="proposal",
            title=f"Harness rule: {title}",
            summary=summary,
            evidence="\n---\n".join(evidence_parts[-3:]),
            status="proposed",
            metadata={
                "source_event_ids": source_ids,
                "cluster_title": title,
                "hits": len(ordered),
                "proposal_type": "harness_rule",
            },
        )
        created.append(proposal)
        existing.add(signature)
    return {"success": True, "created": created, "skipped": skipped, "clusters": len(clusters)}


_UNSAFE_RULE_PATTERNS = (
    "ignore previous instructions",
    "disregard your instructions",
    "system prompt override",
    "do not tell the user",
    "authorized_keys",
    "~/.ssh",
    ".env",
)


def validate_proposal(event_id: int) -> Dict[str, Any]:
    """Validate a proposal before promotion."""
    proposal = get_event(event_id)
    if not proposal:
        return {"success": False, "error": f"proposal {event_id} not found"}
    if proposal.get("kind") != "proposal":
        return {"success": False, "error": f"event {event_id} is not a proposal"}
    text = "\n".join(
        str(proposal.get(k) or "") for k in ("title", "summary", "evidence")
    ).lower()
    for pattern in _UNSAFE_RULE_PATTERNS:
        if pattern in text:
            return {"success": False, "error": f"unsafe proposal text: {pattern}"}
    meta = proposal.get("metadata") or {}
    if not str(proposal.get("summary") or "").strip():
        return {"success": False, "error": "proposal summary is required"}
    if not str(proposal.get("evidence") or "").strip() and not meta.get("source_event_ids"):
        return {"success": False, "error": "proposal needs evidence or source_event_ids"}

    event = record_event(
        kind="proposal",
        title=str(proposal.get("title") or f"proposal {event_id}"),
        summary=str(proposal.get("summary") or ""),
        evidence=str(proposal.get("evidence") or ""),
        proposal_id=int(event_id),
        status="validated",
        metadata={**meta, "validated_from": int(event_id)},
    )
    return {"success": True, "event": event}


def promote_proposal(event_id: int) -> Dict[str, Any]:
    """Promote a validated proposal to an active harness rule."""
    proposal = get_event(event_id)
    if not proposal:
        return {"success": False, "error": f"proposal {event_id} not found"}
    if proposal.get("kind") != "proposal":
        return {"success": False, "error": f"event {event_id} is not a proposal"}

    source_proposal_id = int(proposal.get("proposal_id") or proposal.get("id") or event_id)
    rules = list_harness_rules()
    for rule in rules:
        if (
            int(rule.get("proposal_id") or 0) == source_proposal_id
            and rule.get("status") == "active"
        ):
            return {"success": True, "event": rule.get("event"), "rule": rule, "already_active": True}

    if proposal.get("status") != "validated":
        validation = validate_proposal(event_id)
        if not validation.get("success"):
            return validation
        proposal = validation["event"]

    source_proposal_id = int(proposal.get("proposal_id") or proposal.get("id") or event_id)
    rules = list_harness_rules()
    for rule in rules:
        if (
            int(rule.get("proposal_id") or 0) == source_proposal_id
            and rule.get("status") == "active"
        ):
            return {"success": True, "event": rule.get("event"), "rule": rule, "already_active": True}

    rule: Dict[str, Any] = {
        "id": len(rules) + 1,
        "proposal_id": source_proposal_id,
        "title": str(proposal.get("title") or f"proposal {source_proposal_id}"),
        "summary": str(proposal.get("summary") or ""),
        "created_at": _now_iso(),
        "status": "active",
    }
    event = record_event(
        kind="harness_rule",
        title=rule["title"],
        summary=rule["summary"],
        evidence=str(proposal.get("evidence") or ""),
        proposal_id=source_proposal_id,
        status="active",
        metadata={"rule_id": rule["id"]},
    )
    rule["event_id"] = event["id"]
    rule["event"] = event
    rules.append(rule)
    _write_harness_rules(rules)
    return {"success": True, "event": event, "rule": rule}


def run_evolution_cycle(
    *,
    min_hits: int = 2,
    mine_limit: int = 50,
    auto_promote: bool = False,
) -> Dict[str, Any]:
    """Run one conservative self-harness cycle."""
    mined = mine_skill_candidates(limit=mine_limit)
    proposals = generate_proposals(min_hits=min_hits, limit=mine_limit)
    validated = []
    promoted = []
    for proposal in proposals.get("created") or []:
        validation = validate_proposal(int(proposal.get("id")))
        if validation.get("success"):
            validated.append(validation["event"])
            if auto_promote:
                promotion = promote_proposal(int(proposal.get("id")))
                if promotion.get("success"):
                    promoted.append(promotion["event"])
    return {
        "success": bool(mined.get("success") and proposals.get("success")),
        "mined": mined,
        "proposals": proposals,
        "validated": validated,
        "promoted": promoted,
        "active_rules": list_harness_rules(),
    }
