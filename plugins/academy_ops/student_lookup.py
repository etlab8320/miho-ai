"""Shared PACA student lookup helpers."""

from __future__ import annotations

import re
from typing import Any, Protocol


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
