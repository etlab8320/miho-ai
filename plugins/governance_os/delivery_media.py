"""Media directive preparation for Governance OS final delivery."""

from __future__ import annotations

import re
from typing import Any

_MEDIA_TAG_RE = re.compile(
    r"MEDIA:\s*(?:`([^`\n]+)`|\"([^\"\n]+)\"|'([^'\n]+)'|((?:~/|/)[^\s`\"']+))"
)
_ATTACHMENT_UNAVAILABLE_NOTE = "(첨부 파일을 확인할 수 없어 링크를 제외했습니다)"
_BROKEN_DELIVERY_CLAIM_TERMS = (
    "첨부했습니다",
    "첨부 완료",
    "보냈습니다",
    "전송했습니다",
    "업로드했습니다",
    "전달합니다",
)
_BROKEN_ARTIFACT_CLAIM_TERMS = ("생성했습니다", "만들었습니다", "저장했습니다")
_ARTIFACT_NOUNS = ("파일", "pdf", "mhtml", "리포트", "첨부")


def prepare_delivery_media(
    response_text: str,
    conversation_history: Any = None,
    *,
    user_text: str = "",
) -> str | None:
    """Append omitted tool media directives, then stage unsafe local paths."""

    original = str(response_text or "")
    if not original:
        return None
    artifact_delivery = _complete_artifact_delivery(
        original,
        user_text=user_text,
        conversation_history=conversation_history,
    )
    if artifact_delivery:
        return artifact_delivery
    with_missing_media = _append_missing_media(original, conversation_history)
    repaired = _repair_attachment_paths(with_missing_media)
    final = repaired if repaired is not None else with_missing_media
    return final if final != original else None


def _complete_artifact_delivery(
    response_text: str,
    *,
    user_text: str,
    conversation_history: Any,
) -> str | None:
    try:
        from .delivery_artifacts import complete_artifact_delivery

        return complete_artifact_delivery(
            response_text,
            user_text=user_text,
            conversation_history=conversation_history,
        )
    except Exception:
        return None


def _append_missing_media(response_text: str, conversation_history: Any) -> str:
    if not isinstance(conversation_history, list):
        return response_text
    try:
        from gateway.generated_media import append_missing_generated_media_directives

        return append_missing_generated_media_directives(response_text, conversation_history)
    except Exception:
        return response_text


def _repair_attachment_paths(response_text: str) -> str | None:
    text = str(response_text or "")
    if "MEDIA:" not in text:
        return None
    matches = list(_MEDIA_TAG_RE.finditer(text))
    if not matches:
        return None

    from .final_delivery_repair import repair_artifact_delivery

    replacements: list[tuple[str, str]] = []
    unavailable = False
    for match in matches:
        raw_path = next((group for group in match.groups() if group), "").strip()
        if not raw_path:
            continue
        try:
            repair = repair_artifact_delivery(raw_path)
        except Exception:
            unavailable = True
            replacements.append((match.group(0), _ATTACHMENT_UNAVAILABLE_NOTE))
            continue
        if repair.status == "repaired" and repair.artifact_path and repair.artifact_path != raw_path:
            replacements.append((match.group(0), f"MEDIA:`{repair.artifact_path}`"))
        elif repair.status == "blocked":
            unavailable = True
            replacements.append((match.group(0), _ATTACHMENT_UNAVAILABLE_NOTE))

    if not replacements:
        return None
    result = text
    for old, new in replacements:
        result = result.replace(old, new, 1)
    if unavailable:
        result = _downgrade_unavailable_attachment_claim(result)
    return result


def _downgrade_unavailable_attachment_claim(text: str) -> str:
    kept: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped == _ATTACHMENT_UNAVAILABLE_NOTE:
            continue
        blob = stripped.casefold()
        if any(term in blob for term in _BROKEN_DELIVERY_CLAIM_TERMS):
            continue
        if any(term in blob for term in _BROKEN_ARTIFACT_CLAIM_TERMS) and any(
            noun in blob for noun in _ARTIFACT_NOUNS
        ):
            continue
        kept.append(line)
    kept.append(_ATTACHMENT_UNAVAILABLE_NOTE)
    return "\n".join(kept)
