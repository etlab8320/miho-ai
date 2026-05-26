"""Regression checks against academy natural-language shortcut parsers."""

from __future__ import annotations

from pathlib import Path


RUNTIME_DIR = Path("plugins/academy_ops")
FORBIDDEN_SNIPPETS = (
    "parse_academy_date",
    "draft_intent",
    "extract_trainer_query",
    "student_attendance_quick",
    "re.search(",
    "re.finditer(",
    '"신규" in',
    '"등록" in',
)


def test_academy_runtime_has_no_natural_language_shortcut_parsers() -> None:
    offenders: list[str] = []
    for path in RUNTIME_DIR.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for snippet in FORBIDDEN_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path}:{snippet}")

    assert offenders == []
