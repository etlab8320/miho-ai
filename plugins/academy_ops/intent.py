"""Lightweight intent drafting for PACA/Peak Discord requests."""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import OperationSpec, find_operation


@dataclass(frozen=True)
class IntentDraft:
    operation_key: str
    confidence: float
    needs_confirmation: bool
    message: str

    @property
    def operation(self) -> OperationSpec | None:
        return find_operation(self.operation_key)


_RULES: tuple[tuple[str, tuple[str, ...], float], ...] = (
    ("payment.mark_paid", ("납부 완료", "결제 납부", "카드 결제", "현금 납부"), 0.92),
    ("payment.unpaid", ("미납", "안낸", "미수"), 0.86),
    ("attendance.mark_student", ("출석 처리", "결석 처리", "지각 처리"), 0.88),
    ("attendance.student_month", ("출석", "출결"), 0.78),
    ("plan.by_date", ("운동계획", "운동 계획", "수업계획", "수업 계획"), 0.86),
    ("assignment.by_date", ("반배치", "반 배치", "배정"), 0.84),
    ("consultation.candidates", ("상담할", "상담 후보", "상담 필요"), 0.86),
    ("peak.leaderboard", ("순위", "랭킹", "리더보드"), 0.82),
    ("peak.record_batch", ("기록 입력", "기록 반영", "측정 입력"), 0.86),
    ("peak.student_stats", ("성적", "추세", "기록 떨어", "기록 하락"), 0.82),
    ("peak.records.latest", ("최근 기록", "마지막 기록"), 0.78),
    ("student.search", ("찾아줘", "검색", "누구야"), 0.74),
)


def draft_intent(text: str) -> IntentDraft:
    normalized = " ".join(text.strip().lower().split())
    if not normalized:
        return IntentDraft(
            operation_key="student.search",
            confidence=0.0,
            needs_confirmation=False,
            message="요청 내용을 입력해줘.",
        )

    for operation_key, markers, confidence in _RULES:
        if any(marker in normalized for marker in markers):
            op = find_operation(operation_key)
            needs_confirmation = bool(op and op.requires_confirmation)
            return IntentDraft(
                operation_key=operation_key,
                confidence=confidence,
                needs_confirmation=needs_confirmation,
                message=_draft_message(op, confidence, needs_confirmation),
            )

    return IntentDraft(
        operation_key="student.search",
        confidence=0.45,
        needs_confirmation=False,
        message="학생 검색으로 먼저 확인하고, 부족하면 다시 물어볼게.",
    )


def _draft_message(
    operation: OperationSpec | None,
    confidence: float,
    needs_confirmation: bool,
) -> str:
    if operation is None:
        return "요청을 정확히 분류하지 못했어."

    if needs_confirmation:
        return (
            f"{operation.title}로 이해했어. 실제 반영 전에는 대상과 값을 확인하고 "
            "디스코드 버튼 승인을 받아야 해."
        )

    if confidence < 0.8:
        return f"{operation.title}로 먼저 조회해볼게. 애매하면 선택지를 다시 줄게."

    return f"{operation.title}로 이해했어."
