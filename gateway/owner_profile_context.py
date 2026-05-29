"""Select relevant owner profile context for Discord prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from miho_cli.owner_profile import (
    get_master_profile_path,
    get_timeline_db_path,
    list_profile_events,
    search_profile_events,
)
from miho_constants import get_miho_home

_DEFAULT_MAX_ITEMS = 6
_DEFAULT_MAX_CHARS = 900
_MAX_CANDIDATE_CHARS = 280
_ENTRY_DELIMITER = "\n§\n"
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
_JOSA_SUFFIXES = (
    "기준으로",
    "에서",
    "에게",
    "한테",
    "부터",
    "까지",
    "으로",
    "하고",
    "처럼",
    "보다",
    "이며",
    "이고",
    "이라",
    "라는",
    "을",
    "를",
    "은",
    "는",
    "이",
    "가",
    "와",
    "과",
    "로",
    "에",
    "도",
    "만",
    "랑",
)
_STOP_TOKENS = {
    "오늘",
    "어제",
    "내일",
    "전체",
    "다시",
    "정리",
    "계산",
    "해줘",
    "기준",
    "기준으",
    "하는",
    "해야",
    "한다",
    "있다",
    "없다",
}


@dataclass(frozen=True)
class _Candidate:
    source: str
    text: str
    priority: int


def build_relevant_owner_profile_context(
    query: str,
    *,
    max_items: int = _DEFAULT_MAX_ITEMS,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> str:
    """Return a compact owner profile block relevant to the current turn."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return ""

    scored: list[tuple[int, _Candidate]] = []
    for candidate in _load_candidates(query_tokens):
        score = _score_candidate(query, query_tokens, candidate)
        if score > 0:
            scored.append((score, candidate))
    if not scored:
        return ""

    scored.sort(key=lambda item: (item[0], item[1].priority), reverse=True)
    lines = [
        "### Relevant Owner Profile",
        "Use this as stable owner context for this turn; do not quote it verbatim unless asked.",
    ]
    seen: set[str] = set()
    for _, candidate in scored:
        body = _compact(candidate.text, _MAX_CANDIDATE_CHARS)
        key = body.lower()
        if not body or key in seen:
            continue
        seen.add(key)
        lines.append(f"- [{candidate.source}] {body}")
        if len(lines) - 2 >= max(1, max_items):
            break
    if len(lines) == 2:
        return ""
    return _fit_chars("\n".join(lines), max_chars)


def _load_candidates(query_tokens: set[str]) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    candidates.extend(_user_profile_candidates())
    candidates.extend(_master_profile_candidates())
    candidates.extend(_timeline_candidates(query_tokens))
    return candidates


def _user_profile_candidates() -> list[_Candidate]:
    path = get_miho_home() / "memories" / "USER.md"
    content = _read_existing_text(path)
    if not content:
        return []
    entries = [entry.strip() for entry in content.split(_ENTRY_DELIMITER)]
    return [_Candidate("user", entry, 30) for entry in entries if entry]


def _master_profile_candidates() -> list[_Candidate]:
    content = _read_existing_text(get_master_profile_path())
    if not content:
        return []
    blocks = re.split(r"\n(?=#{1,3}\s)|\n{2,}", content)
    return [
        _Candidate("owner_profile:master", block.strip(), 20)
        for block in blocks
        if block.strip()
    ]


def _timeline_candidates(query_tokens: set[str]) -> list[_Candidate]:
    if not get_timeline_db_path().exists():
        return []
    events = list_profile_events(limit=60)
    seen_ids = {event.get("id") for event in events}
    # Pull older events that match the query so recall isn't capped at the most
    # recent window — otherwise things the owner said long ago are unreachable.
    if query_tokens:
        for event in search_profile_events(sorted(query_tokens), limit=40):
            if event.get("id") not in seen_ids:
                events.append(event)
                seen_ids.add(event.get("id"))
    candidates: list[_Candidate] = []
    for event in events:
        category = str(event.get("category") or "general")
        created_at = str(event.get("created_at") or "")[:10]
        title = str(event.get("title") or "").strip()
        content = str(event.get("content") or "").strip()
        date_prefix = f"{created_at} " if created_at else ""
        text = f"{date_prefix}{title}: {content}".strip(": ")
        if text:
            candidates.append(_Candidate(f"owner_profile:{category}", text, 10))
    return candidates


def _score_candidate(
    query: str,
    query_tokens: set[str],
    candidate: _Candidate,
) -> int:
    text = candidate.text
    candidate_tokens = _tokenize(text)
    overlap = query_tokens & candidate_tokens
    if not overlap:
        return 0
    score = len(overlap) * 10 + min(candidate.priority, 30)
    lowered_text = text.casefold()
    lowered_query = query.casefold()
    for token in overlap:
        if len(token) >= 3 and token in lowered_text and token in lowered_query:
            score += 2
    return score


def _tokenize(value: str) -> set[str]:
    tokens: set[str] = set()
    for raw in _TOKEN_RE.findall(value.casefold()):
        token = _normalize_token(raw)
        if len(token) < 2 or token in _STOP_TOKENS:
            continue
        tokens.add(token)
    return tokens


def _normalize_token(token: str) -> str:
    for suffix in _JOSA_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix) + 1:
            return token[: -len(suffix)]
    return token


def _read_existing_text(path) -> str:
    try:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def _compact(value: str, limit: int) -> str:
    body = " ".join(value.split())
    if len(body) <= limit:
        return body
    return body[: limit - 1].rstrip() + "…"


def _fit_chars(value: str, limit: int) -> str:
    safe_limit = max(0, int(limit or 0))
    if not safe_limit:
        return ""
    if len(value) <= safe_limit:
        return value
    lines: list[str] = []
    used = 0
    for line in value.splitlines():
        extra = len(line) + (1 if lines else 0)
        if used + extra > safe_limit:
            remaining = safe_limit - used - (1 if lines else 0)
            if remaining > 1:
                lines.append(line[: remaining - 1].rstrip() + "…")
            break
        lines.append(line)
        used += extra
    return "\n".join(lines)
