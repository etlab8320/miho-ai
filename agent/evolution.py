"""Public facade for Miho Evolution OS.

The implementation is split by responsibility so runtime modules stay small:
ledger and rollback primitives, harness-rule evolution, and readiness loops.
Importers should keep using ``agent.evolution`` as the stable API surface.
"""

from __future__ import annotations

from .evolution_harness import (
    generate_proposals,
    mine_skill_candidates,
    promote_proposal,
    run_evolution_cycle,
    validate_proposal,
)
from .evolution_ledger import (
    EVENTS_FILENAME,
    HARNESS_RULES_FILENAME,
    VALID_EVENT_KINDS,
    ensure_store,
    events_path,
    evolution_dir,
    get_event,
    harness_rules_path,
    list_events,
    list_harness_rules,
    record_event,
    record_skill_mutation,
    rollback_event,
    snapshot_before_skill_mutation,
    snapshot_skills,
)
from .evolution_training import (
    TRAINING_SCENARIOS,
    evolution_readiness_report,
    run_evolution_autopilot,
    run_immunity_check,
    run_training_ground,
    summarize_events,
)

__all__ = [
    "EVENTS_FILENAME",
    "HARNESS_RULES_FILENAME",
    "TRAINING_SCENARIOS",
    "VALID_EVENT_KINDS",
    "ensure_store",
    "events_path",
    "evolution_dir",
    "evolution_readiness_report",
    "generate_proposals",
    "get_event",
    "harness_rules_path",
    "list_events",
    "list_harness_rules",
    "mine_skill_candidates",
    "promote_proposal",
    "record_event",
    "record_skill_mutation",
    "rollback_event",
    "run_evolution_autopilot",
    "run_evolution_cycle",
    "run_immunity_check",
    "run_training_ground",
    "snapshot_before_skill_mutation",
    "snapshot_skills",
    "summarize_events",
    "validate_proposal",
]
