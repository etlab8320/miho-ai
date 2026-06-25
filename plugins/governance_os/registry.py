"""Registry loader and validator for Governance OS contracts."""

from __future__ import annotations

import json
import hashlib
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
from typing import Any

from .models import AgentRole, Playbook


_REGISTRY_PATH = Path(__file__).with_name("registry.json")


class GovernanceRegistry:
    def __init__(self, *, roles: dict[str, AgentRole], playbooks: dict[str, Playbook]) -> None:
        self.roles = dict(roles)
        self.playbooks = dict(playbooks)

    @property
    def fingerprint(self) -> str:
        return registry_fingerprint(self.to_payload())

    def get_role(self, key: str) -> AgentRole:
        return self.roles[key]

    def get_playbook(self, key: str) -> Playbook:
        return self.playbooks[key]

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": "governance-registry/v1",
            "roles": {key: asdict(role) for key, role in sorted(self.roles.items())},
            "playbooks": {
                key: asdict(playbook) for key, playbook in sorted(self.playbooks.items())
            },
        }
        return json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def validate(self) -> list[str]:
        errors: list[str] = []
        for key, playbook in sorted(self.playbooks.items()):
            if not playbook.domain:
                errors.append(f"playbook {key}: domain is required")
            if not playbook.agent_chain:
                errors.append(f"playbook {key}: agent_chain is required")
            for role_key in playbook.agent_chain:
                if role_key not in self.roles:
                    errors.append(f"playbook {key}: unknown agent {role_key}")
            if not playbook.required_tools and not playbook.forbidden_tools:
                errors.append(f"playbook {key}: tool contract is empty")
            if playbook.review_gates and "result_reviewer" not in playbook.agent_chain:
                errors.append(f"playbook {key}: review gate requires result_reviewer agent")
        return errors


@lru_cache(maxsize=1)
def load_builtin_registry() -> GovernanceRegistry:
    return load_registry(_REGISTRY_PATH)


def load_registry(path: Path) -> GovernanceRegistry:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return registry_from_mapping(raw)


def registry_from_mapping(raw: dict[str, Any]) -> GovernanceRegistry:
    if not isinstance(raw, dict):
        raise ValueError("governance registry root must be a mapping")
    roles = _load_roles(raw.get("roles"))
    playbooks = _load_playbooks(raw.get("playbooks"))
    registry = GovernanceRegistry(roles=roles, playbooks=playbooks)
    errors = registry.validate()
    if errors:
        raise ValueError("; ".join(errors))
    return registry


def registry_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_roles(value: Any) -> dict[str, AgentRole]:
    if not isinstance(value, dict):
        raise ValueError("governance registry roles must be a mapping")
    return {
        str(key): AgentRole.from_mapping(str(key), item)
        for key, item in value.items()
        if isinstance(item, dict)
    }


def _load_playbooks(value: Any) -> dict[str, Playbook]:
    if not isinstance(value, dict):
        raise ValueError("governance registry playbooks must be a mapping")
    return {
        str(key): Playbook.from_mapping(str(key), item)
        for key, item in value.items()
        if isinstance(item, dict)
    }
