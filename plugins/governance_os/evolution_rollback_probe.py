"""Non-destructive Evolution OS rollback probe for Governance readiness."""

from __future__ import annotations

import tempfile
from pathlib import Path


def run_evolution_rollback_probe() -> bool:
    """Verify skill snapshot rollback and harness-rule rollback in a temp home."""
    from miho_constants import reset_miho_home_override, set_miho_home_override

    with tempfile.TemporaryDirectory(prefix="miho-governance-evolution-") as tmp:
        home = Path(tmp) / ".miho"
        skills = home / "skills"
        skills.mkdir(parents=True, exist_ok=True)
        token = set_miho_home_override(home)
        try:
            return _skill_rollback_passes(skills) and _harness_rollback_passes()
        except Exception:
            return False
        finally:
            reset_miho_home_override(token)


def _skill_rollback_passes(skills_dir: Path) -> bool:
    from agent import evolution

    skill_dir = skills_dir / "readiness_probe_skill"
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "---\nname: readiness_probe_skill\ndescription: rollback probe\nversion: 1.0\n---\n\nold\n",
        encoding="utf-8",
    )

    snapshot = evolution.snapshot_skills(reason="governance-readiness-skill-rollback")
    if not snapshot.get("success") or not snapshot.get("event"):
        return False
    skill_file.write_text(
        "---\nname: readiness_probe_skill\ndescription: rollback probe\nversion: 1.0\n---\n\nnew\n",
        encoding="utf-8",
    )

    ok, _msg, data = evolution.rollback_event(int(snapshot["event"]["id"]))
    restored = skill_file.read_text(encoding="utf-8") if skill_file.exists() else ""
    rollback_event = data.get("rollback_event") if isinstance(data, dict) else None
    return (
        ok
        and "\nold\n" in restored
        and isinstance(rollback_event, dict)
        and rollback_event.get("kind") == "rollback"
    )


def _harness_rollback_passes() -> bool:
    from agent import evolution

    proposal = evolution.record_event(
        kind="proposal",
        title="Harness rule: governance rollback readiness",
        summary="Deactivate a harmful harness rule by rolling back its event.",
        evidence="Synthetic Governance OS readiness drill.",
        status="proposed",
        metadata={"governance_readiness_probe": True},
    )
    promotion = evolution.promote_proposal(int(proposal["id"]))
    event = promotion.get("event") if isinstance(promotion, dict) else None
    if not promotion.get("success") or not isinstance(event, dict):
        return False

    ok, _msg, data = evolution.rollback_event(int(event["id"]))
    rollback_event = data.get("rollback_event") if isinstance(data, dict) else None
    rolled_back_rules = [
        rule for rule in evolution.list_harness_rules()
        if rule.get("status") == "rolled_back" and int(rule.get("event_id") or 0) == int(event["id"])
    ]
    return ok and bool(rolled_back_rules) and isinstance(rollback_event, dict)
