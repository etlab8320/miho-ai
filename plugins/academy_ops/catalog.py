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
    OperationSpec(
        key="student.search",
        title="학생 통합 검색",
        domain="student",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/students"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="academy_student_summary와 학생카드 생성에서 사용하는 PACA 학생 검색.",
    ),
    OperationSpec(
        key="student.detail",
        title="학생 상세 요약",
        domain="student",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/students/{id}"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="민감정보를 제거한 학생 카드/요약에만 노출한다.",
    ),
    OperationSpec(
        key="attendance.today_peak",
        title="오늘 피크 출석 현황",
        domain="attendance",
        mode=READ,
        endpoint=EndpointSpec("peak", "GET", "/peak/attendance/students"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="academy_attendance_day와 상담 후보 도구에서 사용하는 일자별 출석 조회.",
    ),
    OperationSpec(
        key="attendance.student_month",
        title="학생 기간별 출석 조회",
        domain="attendance",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/students/{id}/attendance + /paca/schedules"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="LLM이 해석한 student_query/start_date/end_date로 학생별 출석, 지각, 결석, 미체크를 조회한다.",
    ),
    OperationSpec(
        key="peak.records.latest",
        title="최근 운동 기록 조회",
        domain="record",
        mode=READ,
        endpoint=EndpointSpec("peak", "GET", "/peak/records"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="학생 카드의 최근 기록, PB, AVG, 추세 그래프에 사용한다.",
    ),
    OperationSpec(
        key="staff.attendance_day",
        title="강사 출근 목록 조회",
        domain="staff",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/instructors + /paca/instructors/{id}/attendance"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="활성 강사 목록과 강사별 월간 출퇴근 기록을 조합해 특정 일자의 출근 강사를 조회한다.",
    ),
    OperationSpec(
        key="staff.schedule_day",
        title="강사 출근 예정 조회",
        domain="staff",
        mode=READ,
        endpoint=EndpointSpec("peak", "GET", "/peak/assignments"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="Peak 날짜별 배정 데이터에서 예정 강사를 조회한다.",
    ),
    OperationSpec(
        key="plan.by_date",
        title="날짜별 운동계획 조회",
        domain="plan",
        mode=READ,
        endpoint=EndpointSpec("peak", "GET", "/peak/plans"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="date, time_slot 파라미터로 일일 운동계획과 강사 배치를 조회한다.",
    ),
    OperationSpec(
        key="assignment.by_date",
        title="날짜별 반배치 조회",
        domain="assignment",
        mode=READ,
        endpoint=EndpointSpec("peak", "GET", "/peak/assignments"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="LLM이 해석한 date/time_slot로 Peak 반배치, 담당 강사, 배정/미배정 학생을 조회한다.",
    ),
    OperationSpec(
        key="consultation.candidates",
        title="상담 후보 추천",
        domain="consultation",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/consultation-candidates"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="PACA 서버가 재원생, 최근 2주 출결, Peak 최근 5개 기록 추세를 조합한 읽기 전용 후보 목록이다.",
    ),
    OperationSpec(
        key="consultation.note_save",
        title="상담 기록 저장",
        domain="consultation",
        mode=WRITE,
        endpoint=EndpointSpec("local", "INSERT", "academy_ops/consultation_notes.sqlite3"),
        requires_confirmation=False,
        requires_audit_log=True,
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="local_only",
        notes="PACA/Peak에는 쓰지 않고 미호 로컬 학원업무 DB에 학생별 상담 메모를 저장한다.",
    ),
    OperationSpec(
        key="academy.schedule_range",
        title="학원 일정 조회",
        domain="schedule",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/academy-events"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="LLM이 해석한 start_date/end_date 범위로 PACA 업무일정/학원일정 캘린더 이벤트를 조회한다.",
    ),
    OperationSpec(
        key="consultation.schedule_range",
        title="신규 상담 일정 조회",
        domain="consultation",
        mode=READ,
        endpoint=EndpointSpec("paca", "GET", "/paca/consultations"),
        needs_new_backend_api=False,
        implementation_status="implemented",
        api_contract_status="verified_in_plugin",
        notes="LLM이 해석한 start_date/end_date 범위로 PACA 상담 일정을 조회한다.",
    ),
)


OPERATIONS: tuple[OperationSpec, ...] = (
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
        key="report.dashboard",
        title="운영 대시보드 요약",
        domain="report",
        mode=READ,
        endpoint=TBD_ENDPOINT,
        notes="학생 수, 수입/지출, 미납, 휴식 종료 학생 등을 요약한다.",
    ),
)


def all_operations() -> tuple[OperationSpec, ...]:
    return CONNECTED_APIS + OPERATIONS


def find_operation(key: str) -> OperationSpec | None:
    clean = key.strip().lower()
    return next((op for op in all_operations() if op.key == clean), None)


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
        "catalog_status": "partial_live",
        "write_policy": "쓰기 작업은 Discord 확인 버튼과 감사 로그가 붙기 전까지 실행하지 않는다.",
        "api_policy": (
            "읽기 API 일부는 플러그인에서 연결됨. "
            "operations는 아직 남은 학생 카드/운영 자동화 후보 목록이며, "
            "쓰기 기능은 PACA/Peak 백엔드 route, Discord 확인 버튼, 감사 로그를 붙인 뒤 연결한다."
        ),
    }
