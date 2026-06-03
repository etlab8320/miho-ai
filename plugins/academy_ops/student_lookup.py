"""Shared PACA student lookup helpers."""

from __future__ import annotations

import re
from typing import Any, Protocol


FUZZY_MATCH_THRESHOLD = 0.84
FUZZY_MATCH_MARGIN = 0.04


class StudentSearchClient(Protocol):
    def search_paca_students(self, query: str) -> list[dict[str, Any]]: ...


class StudentLookupNotFound(RuntimeError):
    pass


class StudentLookupAmbiguous(RuntimeError):
    def __init__(self, students: list[dict[str, Any]]) -> None:
        self.students = students
        super().__init__(_candidate_text(students))


def resolve_paca_student(client: StudentSearchClient, query: str) -> dict[str, Any]:
    clean = query.strip()
    if not clean:
        raise StudentLookupNotFound
    candidates = _unique_students(client.search_paca_students(clean))
    if not candidates:
        candidates = _fallback_candidates(client, clean)
    if not candidates:
        candidates = _fuzzy_candidates(client, clean)
    return select_paca_student(clean, candidates)


def select_paca_student(query: str, students: list[dict[str, Any]]) -> dict[str, Any]:
    clean = query.strip()
    if not students:
        raise StudentLookupNotFound
    exact = [item for item in students if _field(item, "name") == clean]
    if len(exact) == 1:
        return exact[0]
    if len(students) == 1:
        return students[0]
    matched = _term_matched_students(clean, students)
    if len(matched) == 1:
        return matched[0]
    raise StudentLookupAmbiguous(matched or students)


def candidate_names(students: list[dict[str, Any]]) -> str:
    return _candidate_text(students)


def _fallback_candidates(client: StudentSearchClient, query: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for term in _query_terms(query):
        if term == query:
            continue
        candidates.extend(client.search_paca_students(term))
    return _unique_students(candidates)


def _fuzzy_candidates(client: StudentSearchClient, query: str) -> list[dict[str, Any]]:
    rows = _active_students(client)
    scored = sorted(
        ((score, student) for student in rows if (score := _name_score(query, _field(student, "name"))) > 0),
        key=lambda item: item[0],
        reverse=True,
    )
    if not scored or scored[0][0] < FUZZY_MATCH_THRESHOLD:
        return []
    best_score = scored[0][0]
    return [student for score, student in scored if best_score - score <= FUZZY_MATCH_MARGIN]


def _active_students(client: StudentSearchClient) -> list[dict[str, Any]]:
    list_students = getattr(client, "list_paca_students", None)
    if callable(list_students):
        try:
            return _unique_students(list_students(status="active"))
        except TypeError:
            return _unique_students(list_students())
    return _unique_students(client.search_paca_students(""))


def _name_score(query: str, name: str) -> float:
    clean_query = _normalize(query)
    clean_name = _normalize(name)
    if not clean_query or not clean_name:
        return 0.0
    windows = _comparison_windows(clean_query, len(clean_name))
    return max((_similarity(window, clean_name) for window in windows), default=0.0)


def _comparison_windows(value: str, size: int) -> list[str]:
    if size <= 0:
        return []
    windows = [value]
    if len(value) >= size:
        windows.extend(value[index : index + size] for index in range(len(value) - size + 1))
    return windows


def _similarity(left: str, right: str) -> float:
    left_units = _hangul_units(left)
    right_units = _hangul_units(right)
    if not left_units or not right_units:
        return 0.0
    distance = _edit_distance(left_units, right_units)
    return 1.0 - (distance / max(len(left_units), len(right_units)))


def _hangul_units(value: str) -> list[str]:
    units: list[str] = []
    for char in value:
        code = ord(char)
        if 0xAC00 <= code <= 0xD7A3:
            offset = code - 0xAC00
            units.extend((str(offset // 588), str((offset % 588) // 28), str(offset % 28)))
        else:
            units.append(char)
    return units


def _edit_distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for row_index, left_unit in enumerate(left, start=1):
        current = [row_index]
        for column_index, right_unit in enumerate(right, start=1):
            cost = 0 if left_unit == right_unit else 1
            current.append(
                min(
                    previous[column_index] + 1,
                    current[column_index - 1] + 1,
                    previous[column_index - 1] + cost,
                )
            )
        previous = current
    return previous[-1]


def _term_matched_students(query: str, students: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = _query_terms(query)
    if len(terms) <= 1:
        return []
    return [student for student in students if all(_term_matches_student(term, student) for term in terms)]


def _term_matches_student(term: str, student: dict[str, Any]) -> bool:
    needle = _normalize(term)
    if not needle:
        return False
    fields = ("name", "school", "grade", "grade_type", "student_number", "time_slot", "status")
    return any(needle in _normalize(student.get(field)) for field in fields)


def _query_terms(query: str) -> list[str]:
    return [term for term in (_clean_term(part) for part in query.split()) if term]


def _clean_term(value: str) -> str:
    return value.strip(" .,!?~!ㅋㅎ")


def _normalize(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").lower())


def _unique_students(students: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for student in students:
        if not isinstance(student, dict):
            continue
        key = str(student.get("id") or "")
        if not key:
            key = "|".join(_field(student, field) for field in ("name", "school", "grade"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(student)
    return unique


def _candidate_text(students: list[dict[str, Any]]) -> str:
    return ", ".join(_student_label(student) for student in students[:5])


def _student_label(student: dict[str, Any]) -> str:
    name = _field(student, "name") or "이름 없음"
    profile = " ".join(_field(student, field) for field in ("school", "grade") if _field(student, field))
    return f"{name}({profile})" if profile else name


def _field(student: dict[str, Any], key: str) -> str:
    return str(student.get(key) or "").strip()
