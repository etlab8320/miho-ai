"""PACA/Peak operation catalog for Discord-facing academy workflows."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class EndpointSpec:
    service: str
    method: str
    path: str


@dataclass(frozen=True)
class OperationSpec:
    key: str
    title: str
    domain: str
    mode: str
    endpoint: EndpointSpec
    requires_login: bool = True
    requires_confirmation: bool = False
    requires_audit_log: bool = False
    needs_new_backend_api: bool = False
    notes: str = ""


READ = "read"
WRITE = "write"


OPERATIONS: tuple[OperationSpec, ...] = (
    OperationSpec(
        key="student.search",
        title="학생 통합 검색",
        domain="student",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/students"),
        notes="search 쿼리로 학생을 찾고, 필요하면 상세 조회로 이어간다.",
    ),
    OperationSpec(
        key="student.detail",
        title="학생 상세 요약",
        domain="student",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/students/{student_id}"),
        notes="학생 기본 정보, 최근 수행평가, 최근 결제 상태를 함께 보여준다.",
    ),
    OperationSpec(
        key="attendance.student_month",
        title="학생 월별 출석 조회",
        domain="attendance",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/students/{student_id}/attendance"),
        notes="year_month 파라미터로 월별 출석 요약과 기록을 조회한다.",
    ),
    OperationSpec(
        key="attendance.today_peak",
        title="오늘 피크 출석 현황",
        domain="attendance",
        mode=READ,
        endpoint=EndpointSpec("peak", "GET", "/peak/attendance/students"),
        notes="date 파라미터로 시간대별 출석 현황과 누락 학생을 확인한다.",
    ),
    OperationSpec(
        key="attendance.mark_student",
        title="학생 출석 상태 반영",
        domain="attendance",
        mode=WRITE,
        endpoint=EndpointSpec("peak", "POST", "/peak/attendance/student"),
        requires_confirmation=True,
        requires_audit_log=True,
        notes="present, absent, late, excused 중 하나로 반영한다.",
    ),
    OperationSpec(
        key="payment.unpaid",
        title="미납 조회",
        domain="payment",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/payments/unpaid"),
        notes="로그인 계정의 academyId 범위에서만 미납 목록을 조회한다.",
    ),
    OperationSpec(
        key="payment.mark_paid",
        title="학원비 납부 완료 반영",
        domain="payment",
        mode=WRITE,
        endpoint=EndpointSpec("paca", "POST", "/paca/payments/{payment_id}/pay"),
        requires_confirmation=True,
        requires_audit_log=True,
        notes="결제 대상, 금액, 결제수단, 날짜를 확인한 뒤에만 실행한다.",
    ),
    OperationSpec(
        key="peak.records.latest",
        title="최근 운동 기록 조회",
        domain="record",
        mode=READ,
        endpoint=EndpointSpec("peak", "GET", "/peak/records/latest"),
        notes="학생별 최근 측정 기록을 조회한다.",
    ),
    OperationSpec(
        key="peak.student_stats",
        title="학생 성적/추세 조회",
        domain="record",
        mode=READ,
        endpoint=EndpointSpec("peak", "GET", "/peak/students/{student_id}/stats"),
        notes="기록, 평균, 최고 기록, 점수, 추세를 학생 단위로 조회한다.",
    ),
    OperationSpec(
        key="peak.leaderboard",
        title="종목별 순위 조회",
        domain="record",
        mode=READ,
        endpoint=EndpointSpec("peak", "GET", "/peak/stats/leaderboard/{record_type_id}"),
        notes="종목별 순위와 성별 필터를 조회한다.",
    ),
    OperationSpec(
        key="peak.record_batch",
        title="운동 기록 일괄 입력",
        domain="record",
        mode=WRITE,
        endpoint=EndpointSpec("peak", "POST", "/peak/records/batch"),
        requires_confirmation=True,
        requires_audit_log=True,
        notes="학생, 날짜, 종목, 값을 확인한 뒤 batch upsert로 반영한다.",
    ),
    OperationSpec(
        key="plan.by_date",
        title="날짜별 운동계획 조회",
        domain="plan",
        mode=READ,
        endpoint=EndpointSpec("peak", "GET", "/peak/plans"),
        notes="date, time_slot 파라미터로 일일 운동계획과 강사 배치를 조회한다.",
    ),
    OperationSpec(
        key="assignment.by_date",
        title="날짜별 반배치 조회",
        domain="assignment",
        mode=READ,
        endpoint=EndpointSpec("peak", "GET", "/peak/assignments"),
        notes="date 파라미터로 오전/오후/저녁반 배치와 출석 상태를 조회한다.",
    ),
    OperationSpec(
        key="consultation.candidates",
        title="상담 후보 추천",
        domain="consultation",
        mode=READ,
        endpoint=EndpointSpec("paca+peak", "COMPOSED", "existing read endpoints"),
        notes="출석, 미납, 상담 상태, 피크 기록 추세를 조합한 읽기 전용 분석이다.",
    ),
    OperationSpec(
        key="report.dashboard",
        title="운영 대시보드 요약",
        domain="report",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/reports/dashboard"),
        notes="학생 수, 수입/지출, 미납, 휴식 종료 학생 등을 요약한다.",
    ),
)


def all_operations() -> tuple[OperationSpec, ...]:
    return OPERATIONS


def find_operation(key: str) -> OperationSpec | None:
    clean = key.strip().lower()
    return next((op for op in OPERATIONS if op.key == clean), None)


def grouped_operations() -> dict[str, list[OperationSpec]]:
    groups: dict[str, list[OperationSpec]] = {}
    for op in OPERATIONS:
        groups.setdefault(op.domain, []).append(op)
    return groups


def operations_payload(ops: Iterable[OperationSpec] = OPERATIONS) -> dict[str, object]:
    items = [asdict(op) for op in ops]
    return {
        "operations": items,
        "write_policy": "쓰기 작업은 Discord 확인 버튼과 감사 로그가 붙기 전까지 실행하지 않는다.",
        "api_policy": "1차 범위는 기존 PACA/Peak API를 사용한다.",
    }
