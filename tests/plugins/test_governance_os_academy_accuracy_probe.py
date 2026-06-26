"""Governance readiness coverage for academy tool accuracy."""

from __future__ import annotations

from plugins.governance_os.readiness_academy_probes import (
    academy_accuracy_probe_failures,
)
from plugins.governance_os.registry import load_builtin_registry, registry_from_mapping


def test_academy_accuracy_probe_passes_builtin_registry() -> None:
    assert academy_accuracy_probe_failures(load_builtin_registry()) == []


def test_academy_accuracy_probe_requires_susi_score_playbook() -> None:
    payload = load_builtin_registry().to_payload()
    payload["playbooks"].pop("susi_score_calculation")

    failures = academy_accuracy_probe_failures(registry_from_mapping(payload))

    assert any("susi_score_calculation" in failure for failure in failures)
