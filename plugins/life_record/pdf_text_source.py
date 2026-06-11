"""Deterministic extraction for text-layer school life record PDFs."""

from __future__ import annotations

import re
from typing import Any


def extract_from_pdf_text(page_texts: list[str]) -> dict[str, Any]:
    text = "\n".join(page_texts or [])
    return {
        "identity": _extract_identity(text),
        "attendance": _extract_attendance(text),
        "grades": _extract_grades(text),
        "notes": _extract_notes(text),
        "awards": _extract_awards(text),
    }


def has_core_pdf_text_data(extraction: dict[str, Any]) -> bool:
    identity = extraction.get("identity") or {}
    return bool(identity.get("name") and identity.get("birth6") and extraction.get("grades"))


def _extract_identity(text: str) -> dict[str, Any]:
    class_no, student_no = _latest_class_info(text)
    return {
        "name": _first_match(text, r"성명\s*:\s*([^\n]+)"),
        "school_name": _first_match(text, r"\d{4}년\s*\d{1,2}월\s*\d{1,2}일\s+([^\n]*고등학교)\s+제\d학년\s+입학"),
        "birth6": _first_match(text, r"주민등록번호\s*:\s*(\d{6})-"),
        "class_no": class_no,
        "student_no": student_no,
    }


def _latest_class_info(text: str) -> tuple[str | None, str | None]:
    matches = re.findall(r"반\s*\n\s*(\d+)\s*\n\s*번호\s*\n\s*(\d+)", text)
    if matches:
        return matches[-1]
    header = _section(text, "담임성명", "1. 인적·학적사항")
    numbers = re.findall(r"(?m)^\s*(\d+)\s*$", header)
    if len(numbers) >= 3:
        return numbers[-2], numbers[-1]
    return None, None


def _extract_attendance(text: str) -> list[dict[str, Any]]:
    lines = _lines(_section(text, "2. 출 결 상 황", "3. 수 상 경 력"))
    rows: list[dict[str, Any]] = []
    i = 0
    while i + 1 < len(lines):
        if lines[i] not in {"1", "2", "3"} or not lines[i + 1].isdigit():
            i += 1
            continue
        grade = int(lines[i])
        values: list[str] = []
        i += 1
        while i < len(lines) and not (lines[i] in {"1", "2", "3"} and i + 1 < len(lines) and lines[i + 1].isdigit()):
            values.append(lines[i])
            i += 1
        rows.append(_attendance_row(grade, values))
    return rows


def _attendance_row(grade: int, values: list[str]) -> dict[str, Any]:
    numeric = [value for value in values if value == "." or re.fullmatch(r"\d+", value)]
    notes = [value for value in values if value not in numeric and not value.startswith("원격수업일수")]
    return {
        "grade": grade,
        "school_days": _int(numeric[0] if numeric else None),
        "absence": _joined(numeric[1:4]),
        "late": _joined(numeric[4:7]),
        "early_leave": _joined(numeric[7:10]),
        "special_note": _clean(" ".join(notes)),
    }


def _extract_awards(text: str) -> list[dict[str, Any]]:
    lines = _lines(_section(text, "3. 수 상 경 력", "4. 자격증"))
    rows: list[dict[str, Any]] = []
    for i, value in enumerate(lines):
        if value not in {"1", "2", "3"} or i + 3 >= len(lines):
            continue
        title, date, issuer = lines[i + 1], lines[i + 2], lines[i + 3]
        if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}\.", date):
            rows.append({"grade": int(value), "title": title, "awarded_at": date, "issuer": issuer})
    return rows


def _extract_grades(text: str) -> list[dict[str, Any]]:
    lines = _strip_page_footers(_lines(_section(text, "6. 교과학습발달상황", "8. 행동특성")))
    rows: list[dict[str, Any]] = []
    grade: int | None = None
    semester: int | None = None
    i = 0
    while i < len(lines):
        grade_match = re.fullmatch(r"\[([123])학년\]", lines[i])
        if grade_match:
            grade = int(grade_match.group(1))
            semester = None
            i += 1
            continue
        if lines[i] == "학기":
            marker_idx = _next_semester_marker_index(lines, i + 1)
            if marker_idx is not None:
                semester = int(lines[marker_idx])
                i = marker_idx + 1
                continue
            i += 1
            continue
        if _is_semester_marker(lines, i):
            semester = int(lines[i])
            i += 1
            continue
        if grade is None or i + 4 >= len(lines):
            i += 1
            continue
        parsed = _parse_grade_row(lines, i)
        if not parsed:
            i += 1
            continue
        category, subject, credits, raw_score, achievement, rank, consumed = parsed
        row_semester = _dedupe_semester(rows, grade, semester, subject)
        rows.append(
            {
                "grade": grade,
                "semester": row_semester,
                "category": category,
                "subject": subject,
                "credits": _int(credits),
                "raw_score": raw_score,
                "achievement": achievement,
                "students_count": _students_count(achievement),
                "rank_grade": rank,
            }
        )
        i += consumed
    return rows


def _extract_notes(text: str) -> list[dict[str, Any]]:
    rows = _subject_notes(text)
    rows.extend(_behavior_notes(text))
    return _dedupe_notes(rows)


def _subject_notes(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for grade, section in _grade_sections(text):
        rows.extend(_subject_notes_in_grade(section, grade))
    return rows


def _grade_sections(text: str) -> list[tuple[int | None, str]]:
    matches = list(re.finditer(r"\[([123])학년\]", text))
    if not matches:
        return [(None, text)]
    sections: list[tuple[int | None, str]] = []
    for idx, match in enumerate(matches):
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.append((int(match.group(1)), text[match.end() : end]))
    return sections


def _subject_notes_in_grade(section: str, grade: int | None) -> list[dict[str, Any]]:
    start = _special_note_heading_end(section)
    if start is None:
        return []
    body = section[start:]
    behavior_start = re.search(r"\n\s*8\.\s*행동특성", body)
    if behavior_start:
        body = body[: behavior_start.start()]
    return _parse_subject_note_lines(_strip_note_noise(_lines(body)), grade)


def _special_note_heading_end(text: str) -> int | None:
    match = re.search(r"세\s*부\s*능\s*력\s*및\s*특\s*기\s*사\s*항", text)
    return match.end() if match else None


def _strip_note_noise(lines: list[str]) -> list[str]:
    return [
        line
        for line in lines
        if line not in {"과목", "세 부 능 력 및 특 기 사 항", "세부능력및특기사항"}
        and not re.fullmatch(r"\d+/\d+", line)
        and not re.fullmatch(r"\d{4}년 \d+월 \d+일", line)
        and not re.fullmatch(r"\d+", line)
        and "발급번호" not in line
        and "고등학교" not in line
    ]


def _parse_subject_note_lines(lines: list[str], grade: int | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_body: list[str] = []
    for line in lines:
        marker = _subject_note_marker(line)
        if marker:
            _flush_subject_note(rows, current, current_body)
            semester, subject, first_body = marker
            current = {"grade": grade, "semester": semester, "subject": subject}
            current_body = [first_body]
            continue
        if current:
            current_body.append(line)
    _flush_subject_note(rows, current, current_body)
    return rows


def _subject_note_marker(line: str) -> tuple[int | None, str, str] | None:
    match = re.match(r"^(?:\(([12])학기\))?([가-힣A-Za-zⅠⅡⅢ0-9·・\s]{1,30}):\s*(.*)$", line)
    if not match:
        return None
    subject = _clean(match.group(2))
    if not subject or len(subject) > 20:
        return None
    return _int(match.group(1)), subject, match.group(3)


def _flush_subject_note(rows: list[dict[str, Any]], current: dict[str, Any] | None, body: list[str]) -> None:
    if not current:
        return
    note = _clean_note_text(" ".join(body))
    if len(note) >= 20 and not _is_unavailable_note(note):
        rows.append({**current, "note_text": note})


def _behavior_notes(text: str) -> list[dict[str, Any]]:
    section = _section(text, "8. 행동특성 및 종합의견", None)
    rows: list[dict[str, Any]] = []
    for grade, body in re.findall(r"(?:^|\n)\s*([123])\s*\n(.*?)(?=\n\s*[123]\s*\n|\n\s*주민등록번호|\Z)", section, flags=re.S):
        note = _clean_note_text(body)
        if note and "행동특성" not in note[:30] and not _is_unavailable_note(note):
            rows.append({"grade": int(grade), "semester": None, "subject": "행동특성 및 종합의견", "note_text": note})
    return rows


def _clean_note_text(value: str) -> str:
    text = re.sub(r"반\s+번호\s+이름\s+[가-힣]{2,4}", " ", value)
    text = re.sub(r"[가-힣A-Za-z0-9·・]+고등학교\s+\d+/\d+", " ", text)
    text = re.sub(r"\d{4}년\s+\d+월\s+\d+일\s+발급번호\s+\S+", " ", text)
    text = re.sub(r"발급번호\s+\S+", " ", text)
    return _clean(text)


def _is_unavailable_note(note: str) -> bool:
    return "정보공개" in note and "내부검토" in note and "제공하지 않습니다" in note


def _section(text: str, start: str, end: str | None) -> str:
    s = text.find(start)
    if s < 0:
        return ""
    e = text.find(end, s + len(start)) if end else -1
    return text[s : e if e >= 0 else len(text)]


def _strip_page_footers(lines: list[str]) -> list[str]:
    skip = {"반", "번호", "이름", "비고"}
    return [line for line in lines if line not in skip and not re.fullmatch(r"\d+/\d+", line) and not re.fullmatch(r"\d{4}년 \d+월 \d+일", line)]


def _next_semester(lines: list[str], start: int) -> int | None:
    marker_idx = _next_semester_marker_index(lines, start)
    return int(lines[marker_idx]) if marker_idx is not None else None


def _next_semester_marker_index(lines: list[str], start: int) -> int | None:
    for idx, value in enumerate(lines[start : start + 12], start=start):
        if value in {"1", "2"} and _is_semester_marker(lines, idx):
            return idx
    return None


def _is_semester_marker(lines: list[str], idx: int) -> bool:
    if idx >= len(lines) or lines[idx] not in {"1", "2"}:
        return False
    return _parse_grade_row(lines, idx + 1) is not None


def _parse_grade_row(lines: list[str], idx: int) -> tuple[str, str, str, str, str, str | None, int] | None:
    # NEIS PDF text often wraps category labels like "사회(역사/도덕 포함)"
    # across multiple lines. Find the subject/score columns by their typed shape.
    for subject_idx in range(idx + 1, min(idx + 6, len(lines) - 3)):
        credits = lines[subject_idx + 1]
        raw_score = lines[subject_idx + 2]
        achievement = lines[subject_idx + 3]
        if not _looks_like_grade_row(credits, raw_score, achievement):
            continue
        category = _clean(" ".join(lines[idx:subject_idx]))
        subject = lines[subject_idx]
        rank_idx = subject_idx + 4
        rank = lines[rank_idx] if rank_idx < len(lines) and re.fullmatch(r"\d+", lines[rank_idx]) else None
        consumed = rank_idx - idx + (1 if rank else 0)
        return category, subject, credits, raw_score, achievement, rank, consumed
    return None


def _dedupe_semester(rows: list[dict[str, Any]], grade: int, semester: int | None, subject: str) -> int | None:
    if semester != 1:
        return semester
    duplicate = any(row.get("grade") == grade and row.get("semester") == semester and row.get("subject") == subject for row in rows)
    return 2 if duplicate else semester


def _lines(text: str) -> list[str]:
    return [_clean(line) for line in text.splitlines() if _clean(line)]


def _first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return _clean(match.group(1)) if match else None


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _int(value: str | None) -> int | None:
    return int(value) if value and re.fullmatch(r"\d+", value) else None


def _joined(values: list[str]) -> str:
    return "/".join(values)


def _looks_like_grade_row(credits: str, raw_score: str, achievement: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", credits) and re.fullmatch(r"\d+/.+\(.+\)", raw_score) and re.fullmatch(r"[A-E]\(\d+\)", achievement))


def _students_count(achievement: str) -> int | None:
    match = re.search(r"\((\d+)\)", achievement or "")
    return int(match.group(1)) if match else None


def _dedupe_notes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, str, str]] = set()
    for row in rows:
        key = (row.get("grade"), row.get("semester"), str(row.get("subject") or ""), str(row.get("note_text") or "")[:120])
        if key not in seen:
            seen.add(key)
            out.append(row)
    return out
