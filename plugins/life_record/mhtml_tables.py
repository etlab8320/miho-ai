"""NEIS+ MHTML table extraction for school life records."""

from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
import html
import re
from typing import Any


@dataclass(frozen=True)
class NeisMhtmlTables:
    extraction: dict[str, Any]
    raw_text: str
    html_text: str
    table_count: int
    sections: list[dict[str, Any]]


def extract_neis_mhtml_tables(path: Path) -> NeisMhtmlTables:
    html_text = _mhtml_html(path)
    tables = _extract_tables(html_text)
    raw_text = _html_to_text(html_text)
    extraction = {
        "identity": _extract_identity(raw_text, tables),
        "attendance": _extract_attendance(tables),
        "grades": _extract_grades(tables),
        "notes": _extract_subject_notes(tables) + _extract_creative_activity(tables),
        "awards": [],
    }
    return NeisMhtmlTables(
        extraction=extraction,
        raw_text=raw_text,
        html_text=html_text,
        table_count=len(tables),
        sections=_extract_sections(raw_text),
    )


def _mhtml_html(path: Path) -> str:
    data = path.read_bytes()
    message = BytesParser(policy=policy.default).parsebytes(data)
    parts = message.walk() if message.is_multipart() else [message]
    for part in parts:
        if (part.get_content_type() or "").lower() != "text/html":
            continue
        payload = part.get_payload(decode=True)
        if payload:
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
        content = part.get_content()
        return content if isinstance(content, str) else str(content)
    return ""


class _TextParser(HTMLParser):
    _BREAK_TAGS = {"br", "p", "div", "section", "tr", "table", "h1", "h2", "h3", "li"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.table_depth = 0
        self.in_cell = False
        self.tables: list[list[list[str]]] = []
        self.table: list[list[str]] = []
        self.row: list[str] = []
        self.cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self.table_depth += 1
            if self.table_depth == 1:
                self.table = []
        elif self.table_depth and tag == "tr":
            self.row = []
        elif self.table_depth and tag in {"td", "th"}:
            self.in_cell = True
            self.cell = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.table_depth and tag in {"td", "th"} and self.in_cell:
            self.row.append(_clean(" ".join(self.cell)))
            self.in_cell = False
        elif self.table_depth and tag == "tr":
            if any(self.row):
                self.table.append(self.row)
        elif tag == "table" and self.table_depth:
            if self.table_depth == 1:
                self.tables.append(self.table)
            self.table_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.cell.append(data)


def _html_to_text(html_text: str) -> str:
    parser = _TextParser()
    parser.feed(html_text or "")
    return _clean_multiline("\n".join(parser.parts))


def _extract_tables(html_text: str) -> list[list[list[str]]]:
    parser = _TableParser()
    parser.feed(html_text or "")
    return parser.tables


def _extract_identity(raw_text: str, tables: list[list[list[str]]]) -> dict[str, Any]:
    names = re.findall(r"(?<!담임)성명\s*\n\s*([가-힣]{2,5})", raw_text)
    names += re.findall(r"\b([가-힣]{2,5})\s*님\b", raw_text)
    school_matches = _school_candidates(raw_text)
    birth = _first(raw_text, r"주민등록번호\s*\n\s*(\d{6})-")
    class_no, student_no = _latest_class_info(tables)
    return {
        "name": _best_name(names),
        "school_name": school_matches[-1] if school_matches else None,
        "birth6": birth,
        "class_no": class_no,
        "student_no": student_no,
    }


def _school_candidates(raw_text: str) -> list[str]:
    transfers = re.findall(r"\d{4}년\s+\d{2}월\s+\d{2}일\s+([^\n/]*고등학교)\s+제\d학년\s+전입학", raw_text)
    if transfers:
        return [_clean(school) for school in transfers]
    entries = re.findall(r"\d{4}년\s+\d{2}월\s+\d{2}일\s+([^\n/(]*고등학교)\s+제\d학년\s+입학", raw_text)
    return [_clean(school) for school in entries]


def _best_name(names: list[str]) -> str | None:
    candidates = [_clean(n) for n in names if re.fullmatch(r"[가-힣]{2,5}", _clean(n))]
    if not candidates:
        return None
    return max(candidates, key=lambda value: (len(value), candidates.count(value)))


def _latest_class_info(tables: list[list[list[str]]]) -> tuple[str | None, str | None]:
    for table in tables:
        if table and {"학년", "반", "번호"}.issubset(set(table[0])):
            rows = [row for row in table[1:] if row and row[0].isdigit()]
            if rows:
                last = rows[-1]
                return (last[2] if len(last) > 2 else None, last[3] if len(last) > 3 else None)
    return None, None


def _extract_attendance(tables: list[list[list[str]]]) -> list[dict[str, Any]]:
    table = next((t for t in tables if t and "수업일수" in t[0]), [])
    rows: list[dict[str, Any]] = []
    for row in table[2:]:
        if len(row) < 14 or not row[0].isdigit():
            continue
        nums = [_num(cell) for cell in row[:14]]
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
                "special_note": row[14] if len(row) > 14 else "",
            }
        )
    return rows


def _extract_grades(tables: list[list[list[str]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    grade_table_index = 0
    for table in tables:
        if not table or not _is_grade_header(table[0]):
            continue
        grade = grade_table_index // 3 + 1
        grade_table_index += 1
        for row in table[1:]:
            parsed = _grade_row(row, table[0], grade)
            if parsed:
                rows.append(parsed)
    return rows


def _is_grade_header(header: list[str]) -> bool:
    joined = " ".join(header)
    return "학기" in header and "교과" in header and "과목" in header and "학점수" in header and "성취도" in joined


def _grade_row(row: list[str], header: list[str], grade: int) -> dict[str, Any] | None:
    if len(row) < 5 or not row[0].isdigit():
        return None
    achievement, students = _achievement_count(row[5] if len(row) > 5 else row[4])
    is_achievement_only = "원점수/과목평균" not in " ".join(header)
    return {
        "grade": grade,
        "semester": _num(row[0]),
        "category": row[1],
        "subject": row[2],
        "credits": _float(row[3]),
        "raw_score": "" if is_achievement_only else row[4],
        "achievement": row[4] if is_achievement_only else achievement,
        "students_count": None if is_achievement_only else students,
        "rank_grade": "" if is_achievement_only else (row[6] if len(row) > 6 else ""),
        "raw_row": " / ".join(row),
    }


def _extract_subject_notes(tables: list[list[list[str]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    grade = 0
    grade_table_seen = 0
    for table in tables:
        if table and _is_grade_header(table[0]):
            grade_table_seen += 1
            grade = (grade_table_seen - 1) // 3 + 1
            continue
        if not table or not table[0] or "세부능력 및 특기사항" not in table[0][0]:
            continue
        body = "\n".join(" / ".join(row) for row in table[1:])
        if "당해학년도 학교생활기록은 제공하지 않습니다" in body:
            continue
        rows.extend(_split_subject_notes(body, grade))
    return rows


_NOTE_LABEL = re.compile(r"(?:^|\n| / |\.\s)((?:\([12]학기\))?[가-힣A-Za-z0-9ⅠⅡⅢㆍ·・/\-\s]+?):\s*")


def _split_subject_notes(body: str, grade: int) -> list[dict[str, Any]]:
    matches = list(_NOTE_LABEL.finditer(body))
    rows: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        subject = _clean(match.group(1))
        if not subject or subject in {"주소", "성명", "학교생활기록"}:
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        note = _clean(body[start:end])
        if len(note) < 3:
            continue
        semester = _semester_prefix(subject)
        subject = re.sub(r"^\(([12])학기\)", "", subject).strip()
        rows.append({"grade": grade or None, "semester": semester, "subject": subject, "note_text": note})
    return rows


_CREATIVE_AREAS = ("자율활동", "자율·자치활동", "동아리활동", "진로활동", "봉사활동")


def _extract_creative_activity(tables: list[list[list[str]]]) -> list[dict[str, Any]]:
    """창의적 체험활동(자율·동아리·진로·봉사)을 표[학년·영역·시간·특기사항]에서 추출한다.

    텍스트 정규식 분리(_extract_sections)는 NEIS mhtml 페이지 순서 꼬임에 취약해 창체 본문이
    behavior로 뭉쳐 유실됐다(2026-06-13 실사고). 교과 세특처럼 표 기반으로 뽑아 notes에 합치면
    기존 central_notes 적재 경로로 흘러간다. 학년은 첫 영역 행에만 있고(rowspan) 이후 행은
    비므로 forward-fill 한다. subject는 '창체: {영역}'으로 교과 세특과 구분한다."""
    rows: list[dict[str, Any]] = []
    grade: int | None = None
    for table in tables:
        if not table or not table[0]:
            continue
        header = " ".join(str(c) for c in table[0])
        if "영역" not in header or "특기사항" not in header:
            continue
        for row in table[1:]:
            cells = [str(c).strip() for c in row]
            if cells and cells[0].isdigit():  # 학년 칸이 있으면 갱신, 없으면 직전 학년 유지
                grade = int(cells[0])
                cells = cells[1:]
            if len(cells) < 2:
                continue
            area = next((a for a in _CREATIVE_AREAS if a in cells[0]), None)
            if not area:
                continue
            note = _clean(cells[-1])  # 마지막 칸 = 특기사항 (시간 칸은 버린다)
            if len(note) < 3 or "당해학년도 학교생활기록은 제공하지 않습니다" in note:
                continue
            rows.append({"grade": grade, "semester": None, "subject": f"창체: {area}", "note_text": note})
    return rows


def _extract_sections(raw_text: str) -> list[dict[str, Any]]:
    specs = [
        ("personal_academic", r"1\. 인적·학적사항", r"2\. 출결상황"),
        ("attendance", r"2\. 출결상황", r"3\. 수상경력"),
        ("creative_activity", r"6\. 창의적 체험활동상황", r"7\. 교과학습발달상황"),
        ("subject_development", r"7\. 교과학습발달상황", r"9\. 행동특성 및 종합의견"),
        ("behavior", r"9\. 행동특성 및 종합의견", None),
    ]
    rows = []
    for index, (section_type, start, end) in enumerate(specs, start=1):
        text = _section(raw_text, start, end)
        if text:
            rows.append({"section_type": section_type, "page_start": index, "page_end": index, "raw_text": text})
    return rows


def _section(text: str, start_pat: str, end_pat: str | None) -> str:
    start = re.search(start_pat, text)
    if not start:
        return ""
    if not end_pat:
        return text[start.start() :].strip()
    end = re.search(end_pat, text[start.end() :])
    stop = start.end() + end.start() if end else len(text)
    return text[start.start() : stop].strip()


def _achievement_count(value: str) -> tuple[str, int | None]:
    match = re.match(r"([A-E])\((\d+)\)", value or "")
    return (match.group(1), int(match.group(2))) if match else (value or "", None)


def _semester_prefix(subject: str) -> int | None:
    match = re.match(r"^\(([12])학기\)", subject)
    return int(match.group(1)) if match else None


def _first(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    return _clean(match.group(1)) if match else None


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "").replace("\xa0", " ")).strip()


def _clean_multiline(value: str) -> str:
    text = html.unescape(value or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\x0b\x0c]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _num(value: str | None) -> int:
    value = _clean(value)
    return int(value) if value and value != "." else 0


def _float(value: str | None) -> float | None:
    value = _clean(value)
    if not value:
        return None
    return float(value) if re.fullmatch(r"\d+(?:\.\d+)?", value) else None
