"""Deterministic delivery contract for completed package artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any


_PACKAGE_TOOL_PLAYBOOKS = {
    "academy_hakjong_report_package": "academy_hakjong_report",
    "academy_practical_reco_package": "academy_practical_recommendation",
    "sports_motion_report_package": "sports_motion_analysis",
}
_ARTIFACT_KEYS = ("artifact_path", "file_path", "pdf_path", "document_path", "path")
_USER_VISIBLE_FIELDS = ("message", "delivery_text", "user_safe_message")
_FORBIDDEN_USER_TEXT = (
    "확인되지",
    "전달할 수 없어",
    "검증 완료본으로 확인되지 않음",
    "PDF 대신",
    "미연동",
    "측정 대기",
    "계산 대기",
    "판정 보류",
    "Response truncated",
)
_BLOCKED_DELIVERY_STATUS = {"blocked", "provisional", "retry_required"}


def package_delivery_contract_pass(
    *,
    playbook_key: str,
    tool_name: str,
    payload: dict[str, Any],
    reviewer: dict[str, Any],
) -> bool:
    """Return True only for already-reviewed, deliverable PDF package results."""
    if _PACKAGE_TOOL_PLAYBOOKS.get(str(tool_name or "").strip()) != str(playbook_key or "").strip():
        return False
    if not _is_success(payload):
        return False
    if str(reviewer.get("status") or "").strip() != "pass":
        return False
    artifact_path = _artifact_path(payload)
    if not artifact_path or not _local_artifact_exists(artifact_path):
        return False
    if not _has_media_reference(payload, artifact_path):
        return False
    if _has_errors(payload) or _has_blocked_delivery_status(payload):
        return False
    return not _has_forbidden_user_text(payload)


def _is_success(payload: dict[str, Any]) -> bool:
    return payload.get("ok") is True or payload.get("success") is True


def _artifact_path(payload: dict[str, Any]) -> str:
    for key in _ARTIFACT_KEYS:
        value = str(payload.get(key) or "").strip().strip("`")
        if value:
            return value
    pdf = payload.get("pdf") if isinstance(payload.get("pdf"), dict) else {}
    for key in _ARTIFACT_KEYS:
        value = str(pdf.get(key) or "").strip().strip("`")
        if value:
            return value
    return ""


def _local_artifact_exists(path_text: str) -> bool:
    try:
        path = Path(path_text)
    except (OSError, ValueError):
        return False
    return path.is_file() and path.suffix.lower() == ".pdf"


def _has_media_reference(payload: dict[str, Any], artifact_path: str) -> bool:
    media_tag = str(payload.get("media_tag") or "").strip()
    delivery_text = str(payload.get("delivery_text") or "").strip()
    blob = f"{media_tag}\n{delivery_text}"
    return "MEDIA:" in blob and artifact_path in blob.replace("`", "")


def _has_errors(payload: dict[str, Any]) -> bool:
    errors = payload.get("errors")
    if isinstance(errors, (list, tuple, set)):
        return any(str(item).strip() for item in errors)
    return bool(str(errors or "").strip())


def _has_blocked_delivery_status(payload: dict[str, Any]) -> bool:
    text = str(payload.get("delivery_status") or payload.get("next_action") or "").strip()
    return text.casefold() in _BLOCKED_DELIVERY_STATUS


def _has_forbidden_user_text(payload: dict[str, Any]) -> bool:
    text = "\n".join(str(payload.get(field) or "") for field in _USER_VISIBLE_FIELDS)
    return any(marker in text for marker in _FORBIDDEN_USER_TEXT)
