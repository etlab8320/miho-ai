"""Text parsers for Korean school life record PDFs."""

from __future__ import annotations

import json
import re
from typing import Any

from .utils import clean_line


def extract_field(pattern: str, text: str, default: str = "") -> str:
    match = re.search(pattern, text, re.M)
    return clean_line(match.group(1)) if match else default


def parse_identity(first_page: str, last_page: str) -> dict[str, str]:
    text = first_page + "\n" + last_page
    label_words = {"주민번호", "주민등록번호", "학교코드", "학과", "번호", "성명", "이름"}
    name = ""
    for pattern in [r"성\s*명\s*\n\s*([가-힣]{2,5})", r"이름\s*\n\s*([가-힣]{2,5})"]:
        candidate = extract_field(pattern, last_page)
        if candidate and candidate not in label_words:
            name = candidate
            break
    if not name:
        match = re.search(r"\n(\d+)\s*\n([가-힣]{2,5})\s*\n(\d{6}-\*{7}|\d{6}-\d{7})", first_page)
        if match and match.group(2) not in label_words:
            name = match.group(2)
    if not name:
        candidate = extract_field(r"성명\s*(?:\n|\s)+([가-힣]{2,5})", text)
        name = candidate if candidate not in label_words else ""
    return {
        "name": name or "미상",
        "school_name": extract_field(r"([가-힣A-Za-z0-9]+고등학교)", text),
        "class_no": extract_field(r"반\s*(?:\n|\s)+(\d+)", text),
        "student_no": extract_field(r"번호\s*(?:\n|\s)+(\d+)", text),
        "birth_masked": extract_field(r"(\d{6}-\*{7}|\d{6}-\d{7})", text),
        "document_number": extract_field(r"발급번호\s*[:：]\s*([A-Z0-9\-]+)", text),
        "verification_number": extract_field(r"문서확인번호\s*[:：]\s*([0-9\-]+)", text),
        "issued_at_text": extract_field(r"(20\d{2}년\s*\d{1,2}월\s*\d{1,2}일)", last_page),
    }


def classify_page(text: str) -> str:
    if re.search(r"위 사람의 학교생활기록부.*사본임을 증명|담당부서|고등학교장", text, re.S):
        return "issuer"
    patterns = [
        ("personal_academic", r"인적[·ㆍ]?학적사항"),
        ("attendance", r"출\s*결\s*상\s*황|출결상황"),
        ("course_completion", r"학년도\s*\n학년\s*\n학기\s*\n계열|편제명\s*\n과목명\s*\n시수"),
        ("creative_activity", r"창\s*의\s*적\s*체\s*험\s*활\s*동|자율활동|동아리활동|진로활동|봉사활동"),
        ("behavior", r"행\s*동\s*특\s*성\s*및\s*종\s*합\s*의\s*견|행동특성 및 종합의견"),
        ("subject_development", r"교\s*과\s*학\s*습\s*발\s*달|원점수/과목평균|석차등급|세\s*부\s*능\s*력"),
        ("reading", r"독\s*서\s*활\s*동\s*상\s*황|독서활동상황"),
        ("certificate", r"자격증\s*및\s*인증"),
        ("award", r"수\s*상\s*경\s*력|수상경력"),
    ]
    for section, pattern in patterns:
        if re.search(pattern, text):
            return section
    return "unclassified"


def group_sections(page_texts: list[str]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for page_no, text in enumerate(page_texts, start=1):
        section_type = classify_page(text)
        if current and current["section_type"] == section_type:
            current["page_end"] = page_no
            current["texts"].append(text)
            continue
        if current:
            groups.append(current)
        current = {"section_type": section_type, "page_start": page_no, "page_end": page_no, "texts": [text]}
    if current:
        groups.append(current)
    return [_section_from_group(group) for group in groups]


def _section_from_group(group: dict[str, Any]) -> dict[str, Any]:
    text = "\n\n".join(group.pop("texts"))
    confidence = 0.92 if group["section_type"] != "unclassified" else 0.70
    if len(text) < 50:
        confidence -= 0.15
    if "�" in text:
        confidence -= 0.2
    confidence = max(0.0, min(0.99, confidence))
    return {
        **group,
        "raw_text": text,
        "parsed_json": json.dumps({"method": "page_classification_v1"}, ensure_ascii=False),
        "confidence": confidence,
        "review_status": "needs_review" if confidence < 0.95 else "auto_extracted",
    }


def parse_attendance(first_page: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in first_page.splitlines() if line.strip()]
    rows: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        if line not in {"1", "2", "3"} or idx + 13 >= len(lines):
            continue
        cells = lines[idx : idx + 14]
        if not re.fullmatch(r"\d{2,3}", cells[1] or ""):
            continue
        nums = [_to_int_cell(cell) for cell in cells]
        note_idx = idx + 14
        note = ""
        if note_idx < len(lines) and not re.fullmatch(r"[123]", lines[note_idx]):
            note = lines[note_idx]
        rows.append(
            {
                "grade": nums[0],
                "school_days": nums[1],
                "absent_disease": nums[2],
                "absent_unexcused": nums[3],
                "absent_other": nums[4],
                "late_disease": nums[5],
                "late_unexcused": nums[6],
                "late_other": nums[7],
                "early_leave_disease": nums[8],
                "early_leave_unexcused": nums[9],
                "early_leave_other": nums[10],
                "result_disease": nums[11],
                "result_unexcused": nums[12],
                "result_other": nums[13],
                "special_note": note,
                "confidence": 0.86 if note else 0.84,
            }
        )
    dedup: dict[int, dict[str, Any]] = {}
    for row in rows:
        dedup.setdefault(int(row["grade"]), row)
    return list(dedup.values())


def parse_subject_grades(page_texts: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current_grade: int | None = None
    current_semester: int | None = None
    for text in page_texts:
        lines = _normalize_score_lines([line.strip() for line in text.splitlines() if line.strip()])
        idx = 0
        while idx < len(lines):
            grade_match = re.fullmatch(r"\[(\d)학년\]", lines[idx])
            if grade_match:
                current_grade = int(grade_match.group(1))
                current_semester = None
                idx += 1
                continue
            row, consumed, semester = _parse_grade_row(lines, idx, current_grade, current_semester)
            if row:
                records.append(row)
                current_semester = semester
                idx += consumed
                continue
            idx += 1
    return _dedup_grade_rows(records)


def parse_subject_special_notes(page_texts: list[str]) -> list[dict[str, Any]]:
    parts: list[str] = []
    offsets: list[tuple[int, int]] = []
    pos = 0
    for page_no, text in enumerate(page_texts, start=1):
        offsets.append((pos, page_no))
        clean = _sanitize_note_text(text)
        parts.append(clean)
        pos += len(clean) + 2
    joined = "\n\n".join(parts)
    matches = [m for m in _SUBJECT_LABEL_RE.finditer(joined) if m.group(1).strip() not in _NOTE_NOISE]
    notes: list[dict[str, Any]] = []
    for idx, match in enumerate(matches):
        subject = _clean_subject(match.group(1))
        if not subject:
            continue
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(joined)
        note, note_end = _cut_note(joined[start:end].strip(), start, end)
        if len(note) < 40 or not re.search(r"[가-힣].*(함|임|됨|음|봄|발표|작성|탐구|활동|소감)", note[:800], re.S):
            continue
        notes.append(
            {
                "grade": None,
                "semester": None,
                "subject": subject,
                "note_text": note,
                "source_page_start": _page_for(offsets, match.start()),
                "source_page_end": _page_for(offsets, note_end),
                "confidence": 0.78,
            }
        )
    return notes


def _to_int_cell(value: str) -> int:
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 0


def _normalize_score_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    idx = 0
    while idx < len(lines):
        if idx + 1 < len(lines) and lines[idx].endswith("제2외국") and lines[idx + 1].startswith("어/한문/교양"):
            out.append(lines[idx] + lines[idx + 1])
            idx += 2
            continue
        out.append(lines[idx])
        idx += 1
    return out


KNOWN_CATEGORIES = ["사회(역사/도덕포함)", "기술·가정/제2외국어/한문/교양", "국어", "수학", "영어", "한국사", "과학", "체육", "예술"]


def _split_category_subject(lines: list[str], idx: int) -> tuple[str, str, int]:
    line = lines[idx]
    next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
    for category in sorted(KNOWN_CATEGORIES, key=len, reverse=True):
        if line == category:
            return category, next_line, 2
        if line.startswith(category + " "):
            return category, line[len(category) :].strip(), 1
    return line, next_line, 2


def _parse_grade_row(lines: list[str], idx: int, grade: int | None, semester: int | None) -> tuple[dict[str, Any] | None, int, int | None]:
    offset = 0
    sem = semester
    if lines[idx] in {"1", "2"} and idx + 5 < len(lines):
        sem = int(lines[idx])
        offset = 1
    if sem not in {1, 2} or idx + offset + 4 >= len(lines):
        return None, 0, semester
    base = idx + offset
    category, subject, consumed = _split_category_subject(lines, base)
    credit_idx = base + consumed
    if credit_idx + 2 >= len(lines) or category in _GRADE_HEADERS or subject in _GRADE_HEADERS:
        return None, 0, semester
    credits, score, count = lines[credit_idx : credit_idx + 3]
    if not re.fullmatch(r"\d+(?:\.\d+)?", credits):
        return None, 0, semester
    row = _score_row(grade, sem, category, subject, float(credits), score, count, lines, idx, credit_idx)
    if row:
        return row, max(credit_idx + 3 - idx, 1), sem
    return None, 0, semester


_GRADE_HEADERS = {"학기", "교과", "과목", "학점수", "원점수/과목평균", "성취도", "석차등급", "세 부 능 력 및 특 기 사 항"}
_SCORE_RE = re.compile(r"^\d{1,3}/\d{1,3}(?:\.\d+)?(?:\(\d{1,3}(?:\.\d+)?\))?$")


def _score_row(grade: int | None, sem: int, category: str, subject: str, credits: float, score: str, count: str, lines: list[str], idx: int, credit_idx: int) -> dict[str, Any] | None:
    count_match = re.fullmatch(r"\((\d+)\)", count)
    achievement_match = re.fullmatch(r"([A-E])\((\d+)\)", count)
    if _SCORE_RE.match(score) and count_match:
        rank = lines[credit_idx + 3] if credit_idx + 3 < len(lines) else ""
        return _grade_row(grade, sem, category, subject, credits, score, None, int(count_match.group(1)), rank, lines[idx : credit_idx + 4], 0.84)
    if _SCORE_RE.match(score) and achievement_match:
        return _grade_row(grade, sem, category, subject, credits, score, achievement_match.group(1), int(achievement_match.group(2)), None, lines[idx : credit_idx + 3], 0.82)
    if score in {"A", "B", "C", "D", "E", "P"}:
        return _grade_row(grade, sem, category, subject, credits, None, score, None, None, lines[idx : credit_idx + 2], 0.76)
    return None


def _grade_row(grade: int | None, semester: int, category: str, subject: str, credits: float, raw_score: str | None, achievement: str | None, students_count: int | None, rank: str | None, raw: list[str], confidence: float) -> dict[str, Any]:
    return {"grade": grade, "semester": semester, "category": category, "subject": subject, "credits": credits, "raw_score": raw_score, "achievement": achievement, "students_count": students_count, "rank_grade": rank, "raw_row": " | ".join(raw), "confidence": confidence}


def _dedup_grade_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in records:
        key = (row["grade"], row["semester"], row["category"], row["subject"], row["raw_score"], row["achievement"])
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


_SUBJECT_LABEL_RE = re.compile(r"(?:^|\n)([가-힣A-Za-z0-9ⅠⅡⅢ·\s]{1,24}):\s*")
_NOTE_NOISE = {"학기", "교과", "과목", "학점수", "성취도", "석차등급", "학년도", "학년", "구분명", "학과명", "편제명", "비고", "발급번호", "문서확인번호"}


def _sanitize_note_text(text: str) -> str:
    cleaned: list[str] = []
    for line in [item.strip() for item in text.splitlines() if item.strip()]:
        if line in _NOTE_NOISE or re.fullmatch(r"\d+|\d+/\d+", line):
            continue
        if line.startswith(("문서확인번호", "◆ 본 증명서는", "발급번호")):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def _clean_subject(subject: str) -> str:
    value = re.sub(r"\s+", " ", subject).strip()
    value = re.sub(r"^(?:과목\s+)?세 부 능 력 및 특 기 사 항\s+", "", value).strip()
    if re.search(r"20\d{2}년|문서확인번호|발급번호", value):
        return ""
    return "" if value in _NOTE_NOISE else value


def _cut_note(note: str, start: int, end: int) -> tuple[str, int]:
    cuts = [m.start() for pattern in [r"\n\[2학년\]", r"\n\[3학년\]", r"\n행동특성 및 종합의견", r"\n학년도\n학년"] if (m := re.search(pattern, note))]
    if not cuts:
        return note, end
    cut = min(cuts)
    return note[:cut].strip(), start + cut


def _page_for(offsets: list[tuple[int, int]], offset: int) -> int:
    page = 1
    for start, page_no in offsets:
        if start <= offset:
            page = page_no
        else:
            break
    return page
