"""Shared schema for model-facing tool contracts."""

from __future__ import annotations

from typing import Any


CONTRACT_VERSION = "tool-contract/v2"
REQUIRED_CONTRACT_FIELDS = frozenset(
    {
        "contract_version",
        "kind",
        "domain",
        "purpose",
        "required_inputs",
        "optional_inputs",
        "output",
        "side_effects",
        "reviewer",
        "retry",
        "delivery",
        "blocking_rules",
        "source",
    }
)


def normalize_tool_contract(
    name: str,
    raw: dict[str, Any],
    *,
    source: str,
    kind: str = "tool",
) -> dict[str, Any]:
    """Return a complete contract while preserving legacy keys."""
    args = _list(raw.get("args"))
    required = _list(raw.get("required_inputs")) or _list(raw.get("requires"))
    required = required or _list(raw.get("schema_required"))
    required = required or _default_required_inputs(raw)
    optional = _list(raw.get("optional_inputs")) or [arg for arg in args if arg not in required]
    contract = dict(raw)
    contract.update(
        {
            "contract_version": CONTRACT_VERSION,
            "kind": str(raw.get("kind") or kind),
            "domain": str(raw.get("domain") or "general"),
            "purpose": str(raw.get("purpose") or "").strip(),
            "required_inputs": required,
            "optional_inputs": optional,
            "output": str(raw.get("output") or _default_output(name, raw)).strip(),
            "side_effects": _list(raw.get("side_effects")) or _default_side_effects(name, raw),
            "reviewer": str(raw.get("reviewer") or _default_reviewer(name, raw)).strip(),
            "retry": str(raw.get("retry") or _default_retry(name, raw)).strip(),
            "delivery": str(raw.get("delivery") or _default_delivery(name, raw)).strip(),
            "blocking_rules": _list(raw.get("blocking_rules")),
            "source": source,
        }
    )
    if "requires" not in contract:
        contract["requires"] = required
    if "args" not in contract:
        contract["args"] = args
    return contract


def blocked_capability_contract(name: str, *, source: str = "governance_registry") -> dict[str, Any]:
    """Return a contract for a forbidden tool/capability token."""
    label = str(name or "").strip()
    return normalize_tool_contract(
        label,
        {
            "kind": "blocked_capability",
            "domain": "forbidden",
            "purpose": (
                f"{label} is forbidden in this Governance OS playbook. "
                "Do not call or emulate it; choose the declared required tool path instead."
            ),
            "required_inputs": ["governance playbook decision"],
            "output": "blocked before execution by tool_contract_guard",
            "side_effects": ["none; this capability must not execute"],
            "reviewer": "tool_contract_guard",
            "retry": "replace with the playbook required_tools and rerun review_gates",
            "delivery": "none",
            "blocking_rules": ["never expose this internal block as a final user answer"],
        },
        source=source,
        kind="blocked_capability",
    )


def contract_schema_errors(name: str, contract: dict[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []
    missing = sorted(REQUIRED_CONTRACT_FIELDS - set(contract))
    if missing:
        errors.append(f"{name}: missing fields {', '.join(missing)}")
    for field in ("purpose", "output", "reviewer", "retry", "delivery", "domain"):
        if not str(contract.get(field) or "").strip():
            errors.append(f"{name}: {field} is empty")
    for field in ("required_inputs", "optional_inputs", "side_effects", "blocking_rules"):
        if not isinstance(contract.get(field), list):
            errors.append(f"{name}: {field} must be a list")
    if str(contract.get("kind") or "") == "tool" and not contract.get("required_inputs"):
        errors.append(f"{name}: required_inputs is empty")
    return tuple(errors)


def _list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item or "").strip()]
    return [str(value).strip()] if str(value or "").strip() else []


def _default_required_inputs(raw: dict[str, Any]) -> list[str]:
    if str(raw.get("kind") or "") == "blocked_capability":
        return ["governance playbook decision"]
    return ["user request"]


def _default_output(name: str, raw: dict[str, Any]) -> str:
    domain = str(raw.get("domain") or "")
    if "media" in name:
        return "reviewed media delivery payload"
    if "pdf" in name or "report" in name:
        return "reviewed artifact payload"
    if "score" in name or "recommend" in name:
        return "structured academy result payload"
    if domain == "messaging":
        return "sent message payload"
    return "structured tool result payload"


def _default_side_effects(name: str, raw: dict[str, Any]) -> list[str]:
    if "send" in name or str(raw.get("domain") or "") == "messaging":
        return ["sends a platform message"]
    if "pdf" in name or "report" in name or "image" in name:
        return ["creates local media artifact"]
    if "save" in name or "ingest" in name:
        return ["writes domain data"]
    return ["read-only or computed result"]


def _default_reviewer(name: str, raw: dict[str, Any]) -> str:
    domain = str(raw.get("domain") or "")
    if "media" in name:
        return "attachment_delivery_review"
    if "pdf" in name or "report" in name:
        return "artifact_result_reviewer"
    if domain in {"academy_ops", "susi_ops", "life_record"}:
        return "academy_result_reviewer"
    if domain in {"terminal", "filesystem"}:
        return "dev_result_reviewer"
    return "governance_result_reviewer"


def _default_retry(name: str, raw: dict[str, Any]) -> str:
    if "media" in name:
        return "repair artifact path, then rerun media_delivery_contract"
    if "pdf" in name or "report" in name:
        return "repair content or artifact, rerun same tool, then rerun review_gates"
    if str(raw.get("domain") or "") in {"academy_ops", "susi_ops", "life_record"}:
        return "fix missing inputs or evidence and rerun the same academy tool"
    return "fix missing inputs and rerun the same tool"


def _default_delivery(name: str, raw: dict[str, Any]) -> str:
    if "media" in name:
        return "MEDIA attachment text"
    if "pdf" in name or "report" in name or "image" in name:
        return "artifact path, then media_delivery_contract when user asked for a file"
    if str(raw.get("domain") or "") == "messaging":
        return "platform text response"
    return "Korean summary from reviewed structured result"
