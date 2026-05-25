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
    needs_new_backend_api: bool | None = None
    implementation_status: str = "planned"
    api_contract_status: str = "unverified"
    notes: str = ""


READ = "read"
WRITE = "write"
TBD_ENDPOINT = EndpointSpec("paca/peak", "TBD", "backend route inspection required")


CONNECTED_APIS: tuple[OperationSpec, ...] = (
    OperationSpec(
        key="auth.login",
        title="PACA 로그인 바인딩",
        domain="auth",
        mode=WRITE,
        endpoint=EndpointSpec("paca", "POST", "/paca/auth/login"),
        requires_confirmation=False,
        requires_audit_log=True,
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="Discord 사용자와 PACA/Peak 토큰을 연결하고 로컬 암호화 저장소에 보관한다.",
    ),
)


OPERATIONS: tuple[OperationSpec, ...] = (
    OperationSpec(
        key="student.search",
        title="학생 통합 검색",
        domain="student",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="학생 카드의 첫 축. 실제 PACA/Peak 학생 검색 라우트와 응답 필드를 확인해야 한다.",
    ),
    OperationSpec(
        key="student.detail",
        title="학생 상세 요약",
        domain="student",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="이름, 학년, 소속반, 연락처, 보호자, 재원 상태 같은 카드 기본 필드를 확인한다.",
    ),
    OperationSpec(
        key="attendance.student_month",
        title="학생 월별 출석 조회",
        domain="attendance",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="월별 출석률, 결석/지각 패턴, 최근 출석 추이를 학생 카드에 붙인다.",
    ),
    OperationSpec(
        key="attendance.today_peak",
        title="오늘 피크 출석 현황",
        domain="attendance",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="오늘 출석 현황은 런타임에서 조회된 적이 있지만, 이 플러그인에 API client는 아직 없다.",
    ),
    OperationSpec(
        key="attendance.mark_student",
        title="학생 출석 상태 반영",
        domain="attendance",
        mode=WRITE,
        endpoint=TBD_ENDPOINT,
        requires_confirmation=True,
        requires_audit_log=True,
        notes="쓰기 작업이라 route 확인, 확인 버튼, 감사 로그가 붙기 전까지 실행하면 안 된다.",
    ),
    OperationSpec(
        key="payment.unpaid",
        title="미납 조회",
        domain="payment",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="학생 카드에 미납 여부, 최근 납부, 청구 금액을 보여주려면 실제 결제 API 확인이 필요하다.",
    ),
    OperationSpec(
        key="payment.mark_paid",
        title="학원비 납부 완료 반영",
        domain="payment",
        mode=WRITE,
        endpoint=TBD_ENDPOINT,
        requires_confirmation=True,
        requires_audit_log=True,
        notes="결제 반영은 금액/수단/대상 확인 버튼과 감사 로그 없이는 실행하지 않는다.",
    ),
    OperationSpec(
        key="peak.records.latest",
        title="최근 운동 기록 조회",
        domain="record",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="학생 카드의 운동 기록 요약을 위해 실제 Peak 기록 API를 확인한다.",
    ),
    OperationSpec(
        key="peak.student_stats",
        title="학생 성적/추세 조회",
        domain="record",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="기록, 평균, 최고 기록, 점수, 추세를 학생 단위로 조회한다.",
    ),
    OperationSpec(
        key="peak.leaderboard",
        title="종목별 순위 조회",
        domain="record",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="종목별 순위와 성별 필터를 조회한다.",
    ),
    OperationSpec(
        key="peak.record_batch",
        title="운동 기록 일괄 입력",
        domain="record",
        mode=WRITE,
        endpoint=TBD_ENDPOINT,
        requires_confirmation=True,
        requires_audit_log=True,
        notes="학생, 날짜, 종목, 값을 확인한 뒤 batch upsert로 반영한다.",
    ),
    OperationSpec(
        key="plan.by_date",
        title="날짜별 운동계획 조회",
        domain="plan",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="date, time_slot 파라미터로 일일 운동계획과 강사 배치를 조회한다.",
    ),
    OperationSpec(
        key="assignment.by_date",
        title="날짜별 반배치 조회",
        domain="assignment",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="date 파라미터로 오전/오후/저녁반 배치와 출석 상태를 조회한다.",
    ),
    OperationSpec(
        key="consultation.candidates",
        title="상담 후보 추천",
        domain="consultation",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="출석, 미납, 상담 상태, 피크 기록 추세를 조합한 읽기 전용 분석이다.",
    ),
    OperationSpec(
        key="report.dashboard",
        title="운영 대시보드 요약",
        domain="report",
        mode=READ,
        endpoint=TBD_ENDPOINT,
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
        "connected_apis": [asdict(op) for op in CONNECTED_APIS],
        "operations": items,
        "catalog_status": "roadmap",
        "write_policy": "쓰기 작업은 Discord 확인 버튼과 감사 로그가 붙기 전까지 실행하지 않는다.",
        "api_policy": (
            "현재 플러그인에서 실제 구현된 API는 로그인 바인딩뿐이다. "
            "operations는 학생 카드/운영 자동화를 위한 후보 목록이며, "
            "각 기능은 PACA/Peak 백엔드 route와 응답 필드를 확인한 뒤 연결해야 한다."
        ),
    }
