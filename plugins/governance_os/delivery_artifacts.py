"""Artifact-first final delivery orchestration."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from gateway.attachment_extensions import ATTACHMENT_EXTENSION_PATTERN
from miho_constants import get_miho_home

from .delivery_safety import contains_internal_guard_leak, normalized_blob
from .final_delivery_repair import repair_artifact_delivery

_PATH_RE = re.compile(
    r"(?P<path>(?:/|~/)[^\s`\"']+?\.(?:{ext}))".format(ext=ATTACHMENT_EXTENSION_PATTERN),
    re.IGNORECASE,
)
_ARTIFACT_KEYS = {
    "artifact_path",
    "file_path",
    "document_path",
    "output_path",
    "path",
}
_ARTIFACT_REQUEST_TERMS = (
    "pdf",
    "파일",
    "첨부",
    "보내",
    "전송",
    "정리해서",
    "메타데이터",
    "mhtml",
    "엑셀",
    "리포트",
)
_ARTIFACT_DEFERRAL_TERMS = (
    "확인 가능한 정보로는",
    "확인할 근거",
    "전달하긴 어려",
    "전달할 수 없어",
    "첨부됐는지",
    "검증 완료본",
    "검증 통과본",
    "검증된 완료본",
    "첨부 대신 상태",
    "최종 확정본",
    "확정 첨부본",
    "확정해서 전달",
    "첨부 완료라고 확정",
    "첨부 완료로 안내하지",
    "완료본이라고 전달",
    "확인된 상태가 아니",
    "확정본이 확인되면",
    "실제로 생성",
    "다시 확인",
    "최종 pdf 형태",
    "자료 보내주",
    "원본 파일이나 내용을 보내주",
)
_ARTIFACT_CONFIRMATION_NOUNS = (
    "pdf",
    "파일",
    "첨부",
    "리포트",
    "산출물",
    "완료본",
    "확정본",
    "검증본",
)
_ARTIFACT_NON_DELIVERY_MARKERS = (
    "확인되지",
    "확정할 수 없",
    "전달할 수 없",
    "제공할 수 없",
    "줄 수 없",
    "어려",
    "대기",
    "필요",
    "보내주",
    "확보되면",
    "추측",
    "불가",
)


def complete_artifact_delivery(
    response_text: str,
    *,
    user_text: str,
    conversation_history: Any,
) -> str | None:
    """Return a concrete artifact delivery when the current turn produced one."""

    if not _is_artifact_request(user_text):
        return None
    artifact_path = _latest_artifact_path(conversation_history)
    if not artifact_path:
        return None
    if not _should_complete_artifact_delivery(response_text):
        return None
    repair = repair_artifact_delivery(artifact_path, caption=_caption_for(artifact_path))
    if repair.status == "blocked" or not repair.media_tag:
        return None
    return repair.delivery_text or f"{_caption_for(repair.artifact_path)}\n{repair.media_tag}"


def _is_artifact_request(user_text: str) -> bool:
    user_blob = normalized_blob(user_text)
    return bool(user_blob and any(term in user_blob for term in _ARTIFACT_REQUEST_TERMS))


def _should_complete_artifact_delivery(response_text: str) -> bool:
    response_blob = normalized_blob(response_text)
    if contains_internal_guard_leak(response_text):
        return True
    if any(term in response_blob for term in _ARTIFACT_DEFERRAL_TERMS):
        return True
    if _has_artifact_non_delivery_conflict(response_blob):
        return True
    if "media:" in response_blob:
        return False
    return False


def _has_artifact_non_delivery_conflict(response_blob: str) -> bool:
    if not response_blob:
        return False
    has_artifact = any(noun in response_blob for noun in _ARTIFACT_CONFIRMATION_NOUNS)
    if not has_artifact:
        return False
    return any(marker in response_blob for marker in _ARTIFACT_NON_DELIVERY_MARKERS)


def _latest_artifact_path(conversation_history: Any) -> str:
    candidates: list[str] = []
    for msg in _current_turn_messages(conversation_history):
        if not isinstance(msg, dict) or msg.get("role") not in {"tool", "function"}:
            continue
        content = str(msg.get("content") or "")
        candidates.extend(_structured_paths(content))
        candidates.extend(_safe_raw_paths(content))
    return candidates[-1] if candidates else ""


def _current_turn_messages(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    message_list = [msg for msg in messages if isinstance(msg, dict)]
    last_user_index = -1
    for index, msg in enumerate(message_list):
        if msg.get("role") == "user":
            last_user_index = index
    return message_list[last_user_index + 1 :] if last_user_index >= 0 else message_list


def _structured_paths(content: str) -> list[str]:
    payload = _json_payload(content)
    if not isinstance(payload, dict):
        return []
    paths: list[str] = []
    _collect_structured_paths(payload, paths)
    return [path for path in paths if _existing_file(path)]


def _collect_structured_paths(value: Any, paths: list[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in _ARTIFACT_KEYS and isinstance(child, str):
                paths.append(child)
            else:
                _collect_structured_paths(child, paths)
    elif isinstance(value, list):
        for item in value:
            _collect_structured_paths(item, paths)


def _safe_raw_paths(content: str) -> list[str]:
    paths: list[str] = []
    for match in _PATH_RE.finditer(content):
        path = _clean_path(match.group("path"))
        if _existing_file(path) and _is_safe_raw_artifact_path(path):
            paths.append(path)
    return paths


def _is_safe_raw_artifact_path(path: str) -> bool:
    try:
        resolved = Path(_clean_path(path)).expanduser().resolve(strict=True)
        home = get_miho_home().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        return False
    roots = (
        home / "media_cache",
        home / "cache" / "media",
        home / "discord_exports",
    )
    return any(_path_is_within(resolved, root) for root in roots)


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root.resolve(strict=False))
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _json_payload(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def _existing_file(path: str) -> bool:
    try:
        return Path(_clean_path(path)).expanduser().resolve(strict=True).is_file()
    except (OSError, RuntimeError, ValueError):
        return False


def _clean_path(path: str) -> str:
    clean = str(path or "").strip()
    if len(clean) >= 2 and clean[0] == clean[-1] and clean[0] in "`\"'":
        clean = clean[1:-1].strip()
    return clean.rstrip('",}.)]')


def _caption_for(path: str) -> str:
    suffix = Path(_clean_path(path)).suffix.casefold()
    if suffix == ".pdf":
        return "여기 있어."
    if suffix in {".mhtml", ".mht", ".html", ".htm"}:
        return "정리본 파일입니다."
    return "첨부 파일입니다."
