"""Gateway-side preflight guards for coding requests."""

from __future__ import annotations

import re


_KOREAN_BUILD_REQUEST_RE = re.compile(
    r"(?:"
    r"만들(?:어)?|붙(?:여)?|추가(?:해)?|구현(?:해)?|개발(?:해)?|작성(?:해)?|빌드(?:해)?"
    r")"
    r"(?:\s*(?:줘|주세요|줄래|주라|봐줘|봐|라|자))?"
    r"(?=$|[\s.!?~])"
)
_ENGLISH_BUILD_REQUEST_RE = re.compile(
    r"(?:^|\b(?:please|pls|can\s+you|could\s+you)\s+)"
    r"(?:build|create|make|add|implement)\b",
    re.IGNORECASE,
)
_CODE_TARGET_RE = re.compile(
    r"("
    r"앱|페이지|사이트|웹|서비스|툴|도구|기능|프로젝트|대시보드|시스템|관리|"
    r"상담|다이어리|crm|api|backend|frontend|front[- ]?end|back[- ]?end|"
    r"app|page|site|website|service|tool|feature|dashboard|diary"
    r")",
    re.IGNORECASE,
)
_EXPLICIT_TARGET_RE = re.compile(
    r"("
    r"/Users/|~/|\./|\.\./|projects/|"
    r"레포|repo|repository|폴더|folder|directory|"
    r"여기|현재|이 프로젝트|기존 프로젝트|새 프로젝트|새 폴더"
    r")",
    re.IGNORECASE,
)
_NAMED_PROJECT_TARGET_RE = re.compile(
    r"(?:^|[\s`'\"(])"
    r"[A-Za-z][A-Za-z0-9_.-]{1,80}"
    r"(?:`|'|\")?"
    r"\s*(?:에|에서|쪽에|에다가|로|으로)\b"
)
_ARTIFACT_ONLY_RE = re.compile(
    r"(이미지|그림|사진|카드|리뷰|프리뷰|보고서|포스터|image|photo|poster|report)",
    re.IGNORECASE,
)


TARGET_PROJECT_QUESTION = (
    "어디에 만들까?\n\n"
    "새 프로젝트면 프로젝트 이름이나 폴더를 말해줘. 예: `새 프로젝트 /Users/etlab/projects/diary-app`\n"
    "기존 프로젝트면 프로젝트명을 말해줘. 예: `프로젝트명에 만들어`"
)


def project_target_question_for(text: str | None) -> str | None:
    """Return a Korean preflight question when a coding target is missing."""
    raw = (text or "").strip()
    if not raw or raw.startswith("/"):
        return None
    if _EXPLICIT_TARGET_RE.search(raw) or _NAMED_PROJECT_TARGET_RE.search(raw):
        return None
    if _ARTIFACT_ONLY_RE.search(raw) and not _CODE_TARGET_RE.search(raw):
        return None
    if not (_KOREAN_BUILD_REQUEST_RE.search(raw) or _ENGLISH_BUILD_REQUEST_RE.search(raw)):
        return None
    if not _CODE_TARGET_RE.search(raw):
        return None
    return TARGET_PROJECT_QUESTION
