"""Central student adapter for the recommendation pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import student_records


def grades_from_central(
    database: Path,
    student_query: str,
    *,
    student_id: int | None = None,
) -> tuple[str | None, list[dict[str, Any]]]:
    return student_records.student_grades_from_central(
        student_query,
        student_id=student_id,
        database=database,
    )


def identity_error_message(
    student_query: str,
    *,
    student_id: int | None,
    student_name: str | None,
    status: student_records.StudentResolutionStatus,
) -> str:
    if status is student_records.StudentResolutionStatus.AMBIGUOUS:
        return (
            "같은 이름이나 별칭에 연결된 학생이 여러 명이라 한 명을 확정하지 못했어. "
            "학생의 정확한 전체 이름이나 확인된 학생 번호로 다시 알려줘."
        )
    if status is student_records.StudentResolutionStatus.FOUND:
        return f"{student_name or '해당 학생'}의 확인된 성적이 아직 없어 추천을 계산할 수 없어."
    if student_id is not None:
        return f"확인된 학생 번호 {student_id}에 해당하는 학생을 찾지 못했어."
    return (
        f"'{student_query}'와 정확히 일치하는 학생을 찾지 못했어. "
        "확인된 전체 이름을 쓰거나 해당 학생 상담 스레드에서 다시 요청해줘."
    )


__all__ = ["grades_from_central", "identity_error_message"]
