"""Versioned registry snapshots and rollback support for Governance OS."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from miho_constants import get_miho_home

from .registry import (
    GovernanceRegistry,
    load_builtin_registry,
    registry_fingerprint,
    registry_from_mapping,
)


logger = logging.getLogger(__name__)

SNAPSHOT_SCHEMA = "governance-registry-snapshot/v1"
ACTIVE_SCHEMA = "governance-registry-active/v1"


@dataclass(frozen=True)
class RegistrySnapshot:
    snapshot_id: str
    fingerprint: str
    reason: str
    created_at: str
    path: Path
    payload: dict[str, Any]

    def to_metadata(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "fingerprint": self.fingerprint,
            "reason": self.reason,
            "created_at": self.created_at,
            "path": str(self.path),
        }


@dataclass(frozen=True)
class RegistryActivation:
    snapshot_id: str
    fingerprint: str
    reason: str
    activated_at: str
    path: Path

    def to_metadata(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "fingerprint": self.fingerprint,
            "reason": self.reason,
            "activated_at": self.activated_at,
            "path": str(self.path),
        }


def registry_store_dir(base_dir: Path | None = None) -> Path:
    return base_dir if base_dir is not None else get_miho_home() / "governance_os"


def snapshots_dir(base_dir: Path | None = None) -> Path:
    return registry_store_dir(base_dir) / "registry_snapshots"


def active_registry_path(base_dir: Path | None = None) -> Path:
    return registry_store_dir(base_dir) / "registry_active.json"


def snapshot_registry(
    registry: GovernanceRegistry,
    *,
    reason: str,
    created_at: str = "",
    base_dir: Path | None = None,
    record_event: bool = True,
) -> RegistrySnapshot:
    errors = registry.validate()
    if errors:
        raise ValueError("; ".join(errors))

    created = created_at or _now_iso()
    payload = registry.to_payload()
    fingerprint = registry_fingerprint(payload)
    snapshot_id = _snapshot_id(created, fingerprint)
    path = snapshots_dir(base_dir) / f"{snapshot_id}.json"
    snapshot = RegistrySnapshot(
        snapshot_id=snapshot_id,
        fingerprint=fingerprint,
        reason=reason.strip() or "registry snapshot",
        created_at=created,
        path=path,
        payload=payload,
    )
    _atomic_write_json(path, _snapshot_body(snapshot))
    if record_event:
        _record_snapshot_event(snapshot)
    return snapshot


def read_registry_snapshot(
    snapshot_id: str,
    *,
    base_dir: Path | None = None,
) -> RegistrySnapshot:
    clean_id = _clean_snapshot_id(snapshot_id)
    path = snapshots_dir(base_dir) / f"{clean_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("schema_version") != SNAPSHOT_SCHEMA:
        raise ValueError(f"registry snapshot {clean_id!r} has invalid schema")
    payload = raw.get("payload")
    if not isinstance(payload, dict):
        raise ValueError(f"registry snapshot {clean_id!r} is missing payload")
    registry = registry_from_mapping(payload)
    fingerprint = registry.fingerprint
    if fingerprint != str(raw.get("fingerprint") or ""):
        raise ValueError(f"registry snapshot {clean_id!r} fingerprint mismatch")
    return RegistrySnapshot(
        snapshot_id=clean_id,
        fingerprint=fingerprint,
        reason=str(raw.get("reason") or ""),
        created_at=str(raw.get("created_at") or ""),
        path=path,
        payload=payload,
    )


def activate_registry_snapshot(
    snapshot_id: str,
    *,
    reason: str,
    base_dir: Path | None = None,
    record_event: bool = True,
) -> RegistryActivation:
    snapshot = read_registry_snapshot(snapshot_id, base_dir=base_dir)
    activation = _write_activation(snapshot, reason=reason, base_dir=base_dir)
    if record_event:
        _record_activation_event(activation)
    return activation


def rollback_registry_snapshot(
    snapshot_id: str,
    *,
    reason: str,
    base_dir: Path | None = None,
    record_event: bool = True,
) -> RegistryActivation:
    snapshot = read_registry_snapshot(snapshot_id, base_dir=base_dir)
    activation = _write_activation(snapshot, reason=reason, base_dir=base_dir)
    if record_event:
        _record_rollback_event(activation)
    return activation


def find_promotion_rollback_link(snapshot_id: str) -> dict[str, Any]:
    clean_id = _clean_snapshot_id(snapshot_id)
    from agent import evolution

    for event in evolution.list_events(limit=None, kind="promotion"):
        promotion = _promotion_activation_metadata(event)
        if not promotion:
            continue
        if str(promotion.get("rollback_snapshot_id") or "") == clean_id:
            return _promotion_link_metadata(event, promotion, clean_id)
    return {}


def load_runtime_registry(*, base_dir: Path | None = None) -> GovernanceRegistry:
    path = active_registry_path(base_dir)
    if not path.exists():
        return load_builtin_registry()
    try:
        active = json.loads(path.read_text(encoding="utf-8"))
        snapshot_id = str(active.get("snapshot_id") or "")
        snapshot = read_registry_snapshot(snapshot_id, base_dir=base_dir)
        return registry_from_mapping(snapshot.payload)
    except (OSError, ValueError, json.JSONDecodeError):
        logger.warning("Falling back to builtin governance registry", exc_info=True)
        return load_builtin_registry()


def _write_activation(
    snapshot: RegistrySnapshot,
    *,
    reason: str,
    base_dir: Path | None,
) -> RegistryActivation:
    activation = RegistryActivation(
        snapshot_id=snapshot.snapshot_id,
        fingerprint=snapshot.fingerprint,
        reason=reason.strip() or "activate registry snapshot",
        activated_at=_now_iso(),
        path=active_registry_path(base_dir),
    )
    _atomic_write_json(
        activation.path,
        {
            "schema_version": ACTIVE_SCHEMA,
            "snapshot_id": activation.snapshot_id,
            "fingerprint": activation.fingerprint,
            "reason": activation.reason,
            "activated_at": activation.activated_at,
        },
    )
    return activation


def _snapshot_body(snapshot: RegistrySnapshot) -> dict[str, Any]:
    return {
        "schema_version": SNAPSHOT_SCHEMA,
        "snapshot_id": snapshot.snapshot_id,
        "fingerprint": snapshot.fingerprint,
        "reason": snapshot.reason,
        "created_at": snapshot.created_at,
        "payload": snapshot.payload,
    }


def _record_snapshot_event(snapshot: RegistrySnapshot) -> None:
    from agent import evolution

    evolution.record_event(
        kind="snapshot",
        title=f"Governance registry snapshot {snapshot.snapshot_id}",
        summary=snapshot.reason,
        snapshot_id=snapshot.snapshot_id,
        metadata={"governance_registry_snapshot": snapshot.to_metadata()},
    )


def _record_activation_event(activation: RegistryActivation) -> None:
    from agent import evolution

    evolution.record_event(
        kind="promotion",
        title=f"Governance registry activation {activation.snapshot_id}",
        summary=activation.reason,
        snapshot_id=activation.snapshot_id,
        status="promoted",
        metadata={"governance_registry_activation": activation.to_metadata()},
    )


def _record_rollback_event(activation: RegistryActivation) -> None:
    from agent import evolution

    metadata: dict[str, Any] = {"governance_registry_rollback": activation.to_metadata()}
    promotion_link = _promotion_rollback_link(evolution, activation)
    if promotion_link:
        metadata["governance_promotion_rollback"] = promotion_link
    evolution.record_event(
        kind="rollback",
        title=f"Governance registry rollback {activation.snapshot_id}",
        summary=activation.reason,
        snapshot_id=activation.snapshot_id,
        status="rolled_back",
        metadata=metadata,
    )


def _promotion_rollback_link(evolution_module: Any, activation: RegistryActivation) -> dict[str, Any]:
    for event in evolution_module.list_events(limit=None, kind="promotion"):
        promotion = _promotion_activation_metadata(event)
        if not promotion:
            continue
        if str(promotion.get("rollback_snapshot_id") or "") != activation.snapshot_id:
            continue
        return _promotion_link_metadata(event, promotion, activation.snapshot_id)
    return {}


def _promotion_link_metadata(
    event: dict[str, Any],
    promotion: dict[str, Any],
    rollback_snapshot_id: str,
) -> dict[str, Any]:
    raw_candidate = promotion.get("candidate")
    candidate = cast("dict[str, Any]", raw_candidate) if isinstance(raw_candidate, dict) else {}
    return {
        "target_promotion_event_id": int(event.get("id") or 0),
        "playbook_key": str(candidate.get("playbook_key") or ""),
        "action": str(promotion.get("action") or ""),
        "value": str(promotion.get("value") or ""),
        "promoted_snapshot_id": str(promotion.get("snapshot_id") or ""),
        "rollback_snapshot_id": rollback_snapshot_id,
        "fingerprint": str(promotion.get("fingerprint") or ""),
        "candidate": candidate,
    }


def _promotion_activation_metadata(event: dict[str, Any]) -> dict[str, Any] | None:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return None
    promotion = metadata.get("governance_promotion_activation")
    return promotion if isinstance(promotion, dict) else None


def _snapshot_id(created_at: str, fingerprint: str) -> str:
    stamp = "".join(ch for ch in created_at if ch.isalnum())[:20] or "registry"
    return f"reg-{stamp}-{fingerprint[:12]}"


def _clean_snapshot_id(snapshot_id: str) -> str:
    clean = snapshot_id.strip()
    if not clean or clean != Path(clean).name or ".." in clean:
        raise ValueError("invalid registry snapshot id")
    return clean


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
