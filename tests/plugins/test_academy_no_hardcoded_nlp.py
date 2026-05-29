"""Regression checks against academy natural-language shortcut parsers.

The owner's permanent rule: intent classification is done by the LLM router or
embedding similarity (semantic_intents), never by hardcoded Korean keyword
matching. These checks guard that rule for the academy routing runtime.

Scope note: only plugins/academy_ops is scanned — that is where user-intent
routing lives. gateway/ holds infrastructure (workspace storage, prompts,
profiles) where Korean string literals are legitimate (prompt text, labels),
not intent classification, so scanning it would only add false positives.

The first check is a fixed blacklist (specific parsers/entities we already
removed). The second is a *pattern* check that catches any NEW direct
Korean-substring intent matching on user input — the gap the blacklist alone
could not cover. Keyword fallbacks that route via a marker tuple
(e.g. login_preflight `any(m in text for m in MARKERS)`) are intentionally
allowed: they are an embedding-first fallback, and they don't match a literal
Korean string directly against the input.
"""

from __future__ import annotations

import re
from pathlib import Path


RUNTIME_DIR = Path("plugins/academy_ops")
FORBIDDEN_SNIPPETS = (
    "parse_academy_date",
    "draft_intent",
    "extract_trainer_query",
    "student_attendance_quick",
    "re.search(",
    "re.finditer(",
    "re.match(",
    "re.fullmatch(",
    "제멀",
    "여민석",
    "제자리멀리뛰기",
    "오철민",
    '"신규" in',
    '"등록" in',
)

# Matches a Korean-containing string literal tested directly against a
# user-input variable, e.g. `"출석" in text` or `any("출석" in query ...)`.
# Targets user-input variable names only; `message` is excluded because in this
# codebase it denotes a tool's *response* payload (see
# natural_router._is_login_required_payload), not user input.
_KOREAN_SUBSTRING_INTENT = re.compile(
    r"""["'][^"']*[가-힣][^"']*["']\s+in\s+\b"""
    r"""(text|query|content|msg|utterance|user_text|user_input|raw_text)\b"""
)


def test_academy_runtime_has_no_natural_language_shortcut_parsers() -> None:
    offenders: list[str] = []
    for path in RUNTIME_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for snippet in FORBIDDEN_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path}:{snippet}")

    assert offenders == [], f"forbidden NLP-shortcut snippets found: {offenders}"


def test_academy_runtime_has_no_direct_korean_substring_intent_matching() -> None:
    offenders: list[str] = []
    for path in RUNTIME_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for match in _KOREAN_SUBSTRING_INTENT.finditer(text):
            offenders.append(f"{path}: {match.group(0)!r}")

    assert offenders == [], (
        "direct Korean-keyword intent matching on user input is forbidden; "
        f"route intent through the LLM router or semantic_intents instead: {offenders}"
    )


def test_korean_substring_detector_is_effective() -> None:
    # Self-check: the detector must catch a real violation...
    assert _KOREAN_SUBSTRING_INTENT.search('if "출석" in text:')
    assert _KOREAN_SUBSTRING_INTENT.search('any("등록" in query for x in y)')
    # ...and must NOT flag the allowed marker-tuple fallback or response checks.
    assert not _KOREAN_SUBSTRING_INTENT.search("any(m in text for m in MARKERS)")
    assert not _KOREAN_SUBSTRING_INTENT.search('"학원 계정 연결" in message')
    assert not _KOREAN_SUBSTRING_INTENT.search('"hello" in text')
