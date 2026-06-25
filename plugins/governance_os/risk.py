"""Deterministic risk judge for Governance OS requests."""

from __future__ import annotations

from typing import Any

from .models import PolicyDecision
from .registry import GovernanceRegistry


_APPROVAL_CONTEXT = {"explicit_approval", "owner_approved", "approval_granted"}
_HIGH_RISK_TERMS = (
    "production",
    "prod",
    "deploy",
    "restart",
    "rollback",
    "migration",
    "credential",
    "secret",
    "프로덕션",
    "운영",
    "배포",
    "재시작",
    "롤백",
    "마이그레이션",
    "비밀키",
    "토큰",
)
_SENSITIVE_MEMORY_TERMS = (
    "주민번호",
    "비밀번호",
    "api key",
    "secret",
    "token",
    "raw_sensitive_data",
)


def evaluate_request_risk(
    registry: GovernanceRegistry,
    *,
    playbook_key: str,
    user_text: str,
    available_context: tuple[str, ...] = (),
    tool_name: str = "",
    args: dict[str, Any] | None = None,
) -> PolicyDecision:
    del registry, args
    context = {item.strip() for item in available_context if item.strip()}
    blob = f"{playbook_key} {tool_name} {user_text}".casefold()
    if context & _APPROVAL_CONTEXT:
        return _allow(playbook_key, tool_name, "explicit_approval_present")
    if _requires_approval(playbook_key, blob):
        return PolicyDecision(
            action="require_approval",
            reason="approval_required",
            playbook_key=playbook_key,
            agent_key="risk_judge",
            tool_name=tool_name,
            message_ko=(
                "이 요청은 운영 변경이나 민감한 작업 가능성이 있어 명시적 승인 후 진행해야 합니다. "
                "테스트 결과와 롤백 방법을 먼저 확인하고 승인 여부를 받아야 합니다."
            ),
            evidence=(f"risk_judge matched high-risk request for {playbook_key}",),
        )
    return _allow(playbook_key, tool_name, "risk_accepted")


def _requires_approval(playbook_key: str, blob: str) -> bool:
    if playbook_key == "dev_code_update" and any(term in blob for term in _HIGH_RISK_TERMS):
        return True
    if playbook_key == "memory_policy_update" and any(
        term in blob for term in _SENSITIVE_MEMORY_TERMS
    ):
        return True
    return False


def _allow(playbook_key: str, tool_name: str, reason: str) -> PolicyDecision:
    return PolicyDecision(
        action="allow",
        reason=reason,
        playbook_key=playbook_key,
        agent_key="risk_judge",
        tool_name=tool_name,
        message_ko="",
    )
