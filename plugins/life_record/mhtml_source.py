"""Deterministic NEIS MHTML source-text extraction helpers."""

from __future__ import annotations

import re
from typing import Any


def extract_from_mhtml_source(page_texts: list[str]) -> dict[str, Any]:
    text = "\n".join(page_texts or [])
    return {
        "identity": _extract_identity(text),
        "attendance": _extract_attendance(text),
        "grades": _extract_grades(text),
        "notes": _extract_notes(text),
        "awards": [],
    }


def empty_extraction() -> dict[str, Any]:
    return {"identity": {}, "attendance": [], "grades": [], "notes": [], "awards": []}


def _extract_identity(text: str) -> dict[str, Any]:
    section = _section(text, "1. 인적·학적사항", "2. 출결상황")
    name = _after_label(section, "성명")
    birth = _first_match(section, r"주민등록번호\s*\n\s*(\d{6})-")
    school = _first_match(text, r"\d{4}년\s*\d{2}월\s*\d{2}일\s+([^\n]*고등학교)\s+제\d학년\s+입학")
    class_no, student_no = _latest_class_info(text)
    return {
        "name": name,
        "school_name": school,
        "birth6": birth,
        "class_no": class_no,
        "student_no": student_no,
    }


def _latest_class_info(text: str) -> tuple[str | None, str | None]:
    section = _section(text, "학반정보", "1. 인적·학적사항")
    numbers = re.findall(r"(?m)^\s*(\d+)\s*$", section)
    if len(numbers) < 4:
        return None, None
    rows = [numbers[i : i + 3] for i in range(0, len(numbers), 3)]
    last = rows[-1]
    return (last[1], last[2]) if len(last) >= 3 else (None, None)


def _extract_attendance(text: str) -> list[dict[str, Any]]:
    section = _section(text, "2. 출결상황", "3. 수상경력")
    lines = _lines(section)
    rows: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        if lines[i] not in {"1", "2", "3"} or i + 1 >= len(lines) or not lines[i + 1].isdigit():
            i += 1
            continue
        grade = int(lines[i])
        values: list[str] = []
        i += 1
        while i < len(lines) and not (lines[i] in {"1", "2", "3"} and i + 1 < len(lines) and lines[i + 1].isdigit()):
            if lines[i] == "." or re.fullmatch(r"\d+", lines[i]):
                values.append(lines[i])
            i += 1
        if len(values) >= 13:
            rows.append(
                {
                    "grade": grade,
                    "school_days": _int(values[0]),
                    "absence": _joined(values[1:4]),
                    "late": _joined(values[4:7]),
                    "early_leave": _joined(values[7:10]),
                    "special_note": _joined(values[10:13]),
                }
            )
    return rows


def _extract_grades(text: str) -> list[dict[str, Any]]:
    section = _section(text, "7. 교과학습발달상황", "세부능력 및 특기사항")
    lines = _lines(section)
    rows: list[dict[str, Any]] = []
    grade = None
    i = 0
    while i < len(lines):
        grade_match = re.fullmatch(r"([123])학년", lines[i])
        if grade_match:
            grade = int(grade_match.group(1))
            i += 1
            continue
        if grade is None or lines[i] not in {"1", "2"} or i + 5 >= len(lines):
            i += 1
            continue
        semester, category, subject, credits, raw_score, achievement = lines[i : i + 6]
        if not _looks_like_grade_row(credits, raw_score, achievement):
            i += 1
            continue
        next_index = i + 6
        rank = (
            lines[next_index]
            if next_index < len(lines) and re.fullmatch(r"\d+", lines[next_index]) and not _is_grade_row_at(lines, next_index)
            else None
        )
        rows.append(
            {
                "grade": grade,
                "semester": int(semester),
                "category": category,
                "subject": subject,
                "credits": _int(credits),
                "raw_score": raw_score,
                "achievement": achievement,
                "students_count": _students_count(achievement),
                "rank_grade": rank,
            }
        )
        i += 7 if rank else 6
    return rows


def _extract_notes(text: str) -> list[dict[str, Any]]:
    rows = _activity_notes(text)
    rows.extend(_subject_notes(text))
    rows.extend(_behavior_notes(text))
    return _dedupe_notes(rows)


def _activity_notes(text: str) -> list[dict[str, Any]]:
    section = _section(text, "6. 창의적 체험활동상황", "7. 교과학습발달상황")
    lines = _lines(section)
    rows: list[dict[str, Any]] = []
    grade: int | None = None
    i = 0
    while i < len(lines):
        if lines[i] in {"1", "2", "3"}:
            grade = int(lines[i])
            i += 1
            continue
        if lines[i] not in {"자율활동", "동아리활동", "진로활동"} or grade is None:
            i += 1
            continue
        area = lines[i]
        i += 1
        if i < len(lines) and re.fullmatch(r"\d+", lines[i]):
            i += 1
        body: list[str] = []
        while i < len(lines) and lines[i] not in {"1", "2", "3", "자율활동", "동아리활동", "진로활동"}:
            body.append(lines[i])
            i += 1
        note = _clean(" ".join(body))
        if note:
            rows.append({"grade": grade, "semester": None, "subject": f"창체: {area}", "note_text": note})
    return rows


def _subject_notes(text: str) -> list[dict[str, Any]]:
    section = _section(text, "세부능력 및 특기사항", "9. 행동특성 및 종합의견")
    pattern = re.compile(r"(?:^|\n)([가-힣A-Za-zⅠⅡⅢ0-9·・\s]{1,30}):\s*(.*?)(?=\n[가-힣A-Za-zⅠⅡⅢ0-9·・\s]{1,30}:\s|\n\s*8\. 독서|\n\s*9\. 행동|\Z)", re.S)
    rows: list[dict[str, Any]] = []
    for match in pattern.finditer(section):
        subject = _clean(match.group(1))
        note = _clean(match.group(2))
        if subject and note and len(note) >= 20 and subject != "희망분야":
            rows.append({"grade": None, "semester": None, "subject": subject, "note_text": note})
    return rows


def _behavior_notes(text: str) -> list[dict[str, Any]]:
    section = _section(text, "9. 행동특성 및 종합의견", "개인정보처리방침")
    rows: list[dict[str, Any]] = []
    for grade, body in re.findall(r"(?:^|\n)\s*([123])\s*\n(.*?)(?=\n\s*[123]\s*\n|\Z)", section, flags=re.S):
        note = _clean(body)
        if note:
            rows.append({"grade": int(grade), "semester": None, "subject": "행동특성 및 종합의견", "note_text": note})
    return rows


def _section(text: str, start: str, end: str | None) -> str:
    starts = [match.start() for match in re.finditer(re.escape(start), text)]
    if not starts:
        return ""
    s = starts[-1]
    e = text.find(end, s + len(start)) if end else -1
    return text[s : e if e >= 0 else len(text)]


def _after_label(text: str, label: str) -> str | None:
    return _first_match(text, rf"{re.escape(label)}\s*\n\s*([^\n]+)")


def _first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return _clean(match.group(1)) if match else None


def _lines(text: str) -> list[str]:
    return [_clean(line) for line in text.splitlines() if _clean(line)]


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _int(value: str | None) -> int | None:
    if value is None or value == ".":
        return None
    return int(value) if re.fullmatch(r"\d+", value) else None


def _joined(values: list[str]) -> str:
    return "/".join(values)


def _looks_like_grade_row(credits: str, raw_score: str, achievement: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", credits) and re.fullmatch(r"\d+/.+\(.+\)", raw_score) and re.fullmatch(r"[A-E]\(\d+\)", achievement))


def _is_grade_row_at(lines: list[str], index: int) -> bool:
    return (
        index + 5 < len(lines)
        and lines[index] in {"1", "2"}
        and _looks_like_grade_row(lines[index + 3], lines[index + 4], lines[index + 5])
    )


def _students_count(achievement: str) -> int | None:
    match = re.search(r"\((\d+)\)", achievement or "")
    return int(match.group(1)) if match else None


def _dedupe_notes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, str]] = set()
    for row in rows:
        key = (row.get("grade"), row.get("subject"), str(row.get("note_text") or "")[:120])
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out
