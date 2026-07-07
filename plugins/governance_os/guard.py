"""Pre-tool guard backed by Governance OS playbook contracts."""

from __future__ import annotations

import json
from typing import Any

from .policy import _forbidden_tool_message, evaluate_tool_call
from .versioning import load_runtime_registry


_GOVERNANCE_DEV_TARGETS = (
    "plugins/governance_os",
    "plugins.governance_os",
    "tests/plugins/test_governance_os",
    "tests/e2e/test_governance_os",
    "tests/e2e/test_discord_governance_delivery.py",
    "docs/governance-os",
    "governance_os",
    "miho governance",
)
_DEV_VERIFICATION_COMMANDS = (
    "miho governance ",
    ".venv/bin/miho governance ",
    "python -m pytest",
    "pytest ",
    "pytest\n",
    "rg ",
    "git diff",
    "git status",
    "sed -n",
    "nl -ba",
    "wc -l",
    "python - <<",
)
_DESTRUCTIVE_COMMAND_MARKERS = (
    "git reset",
    "git checkout --",
    "rm -rf",
)
_ARTIFACT_GENERATION_MARKERS = (
    "reportlab",
    "weasyprint",
    "fpdf",
    "chromium",
    "write_file",
    "open(",
    ".write(",
    "직접 생성",
    "직접 만들",
    "생성 완료",
    "작성 완료",
    "첨부 완료",
    "완료했습니다",
    "파일 생성",
    "pdf 생성",
    "리포트 생성",
    "추천 pdf",
)


def governance_pre_tool_call(tool_name: Any = None, args: Any = None, **context: Any) -> dict[str, str] | None:
    name = str(tool_name or "").strip()
    if not name:
        return None
    registry = load_runtime_registry()
    turn_text = _turn_text(context)
    payload = _search_blob({"args": args, "turn_text": turn_text})
    if _is_pytest_verification_call(name, payload):
        return None
    if _is_governance_dev_verification_call(name, args, registry=registry, payload=payload):
        return None
    if name == "terminal" and any(marker in payload for marker in _DESTRUCTIVE_COMMAND_MARKERS):
        return {"action": "block", "message": _forbidden_tool_message(())}
    matching_playbooks = [
        playbook for playbook in registry.playbooks.values() if _matches_playbook_contract(payload, playbook)
    ]
    specific_playbook_allows_tool = any(
        playbook.key != "designed_pdf_artifact" and name not in playbook.forbidden_tools
        for playbook in matching_playbooks
    )
    if specific_playbook_allows_tool:
        return None
    for playbook in registry.playbooks.values():
        if specific_playbook_allows_tool and playbook.key == "designed_pdf_artifact":
            continue
        if name not in playbook.forbidden_tools:
            continue
        if not _matches_playbook_contract(payload, playbook):
            continue
        if not (_matches_playbook_contract(turn_text, playbook) or _looks_like_artifact_bypass(payload)):
            continue
        decision = evaluate_tool_call(
            registry,
            playbook_key=playbook.key,
            tool_name=name,
            args=args if isinstance(args, dict) else {},
        )
        if decision.action == "block":
            return {"action": "block", "message": decision.message_ko}
    return None


def _is_governance_dev_verification_call(
    tool_name: str,
    args: Any,
    *,
    registry: Any,
    payload: str,
) -> bool:
    name = tool_name.casefold().strip()
    blob = payload or _search_blob(args)
    if not any(target in blob for target in _GOVERNANCE_DEV_TARGETS):
        return False
    if any(marker in blob for marker in _DESTRUCTIVE_COMMAND_MARKERS):
        return False
    if _matches_non_dev_artifact_generation(registry, blob):
        return False
    if name in {"read_file", "search_files"}:
        return True
    if name != "terminal":
        return False
    return any(marker in blob for marker in _DEV_VERIFICATION_COMMANDS)


def _is_pytest_verification_call(tool_name: str, payload: str) -> bool:
    """Allow repository test commands even when test names mention governed domains."""

    if tool_name.casefold().strip() != "terminal":
        return False
    blob = payload or ""
    if any(marker in blob for marker in _DESTRUCTIVE_COMMAND_MARKERS):
        return False
    if "tests/" not in blob:
        return False
    return any(marker in blob for marker in ("python -m pytest", "pytest ", "pytest\n", ".venv/bin/python -m pytest"))


def _matches_non_dev_artifact_generation(registry: Any, blob: str) -> bool:
    if not any(marker in blob for marker in _ARTIFACT_GENERATION_MARKERS):
        return False
    for playbook in registry.playbooks.values():
        if getattr(playbook, "domain", "") == "dev":
            continue
        if _matches_playbook_contract(blob, playbook) and _looks_like_artifact_bypass(blob):
            return True
    return False



def _looks_like_artifact_bypass(blob: str) -> bool:
    markers = (
        ".pdf",
        "pdf",
        ".xlsx",
        "excel",
        "엑셀",
        "reportlab",
        "weasyprint",
        "fpdf",
        "chromium",
        "html",
        "파일 생성",
        "직접 만들",
        "직접 생성",
        "직접 계산",
        "환산",
    )
    return any(marker in blob for marker in markers)


def _matches_playbook(blob: str, triggers: tuple[str, ...]) -> bool:
    if not blob:
        return False
    for trigger in triggers:
        needle = trigger.casefold().strip()
        if needle and needle in blob:
            return True
        words = [part for part in needle.split() if len(part) >= 2]
        if len(words) >= 2 and all(word in blob for word in words):
            return True
    return False


def _matches_playbook_contract(blob: str, playbook: Any) -> bool:
    return _matches_playbook(blob, playbook.triggers) or str(playbook.key or "").casefold() in blob


def _turn_text(context: dict[str, Any]) -> str:
    for key in ("user_text", "user_message", "original_user_message"):
        text = str(context.get(key) or "").casefold().strip()
        if text:
            return text
    try:
        from agent.turn_context import current_user_message

        return str(current_user_message() or "").casefold().strip()
    except Exception:
        return ""


def _search_blob(value: Any) -> str:
    try:
        return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, default=str).casefold()
    except (TypeError, ValueError):
        return str(value or "").casefold()
