"""Tool registry and contracts for academy natural routing."""

from __future__ import annotations

from typing import Any, Callable

from .academy_calendar_tool import (
    _academy_schedule_range_tool_handler,
    _class_roster_range_tool_handler,
    _consultation_schedule_range_tool_handler,
)
from .academy_query_tools import (
    _attendance_day_tool_handler,
    _consultation_candidates_tool_handler,
    _plan_by_date_tool_handler,
    _student_summary_tool_handler,
)
from .assignment_tool import _assignment_by_date_tool_handler
from .attendance_calendar_tool import _student_attendance_calendar_image_tool_handler
from .brand_logo_tool import (
    _academy_reset_brand_logo_tool_handler,
    _academy_set_brand_logo_tool_handler,
)
from .consultation_notes_tool import _consultation_note_save_tool_handler
from .monthly_test_records_tool import _monthly_test_records_tool_handler
from .staff_attendance_tool import (
    _staff_attendance_day_tool_handler,
    _staff_attendance_range_tool_handler,
)
from .staff_schedule_tool import _staff_schedule_day_tool_handler
from .student_attendance_tool import _student_attendance_range_tool_handler
from .student_card_tool import _student_card_image_tool_handler
from .student_context_tool import _student_context_tool_handler
from .student_record_chart_tool import _student_record_chart_image_tool_handler
from .student_record_cohort_tool import _student_record_cohort_tool_handler
from .student_records_tool import _student_record_lookup_tool_handler
from .thread_roster_tool import _thread_roster_lookup_tool_handler


ToolHandler = Callable[..., str]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    "academy_schedule_range": _academy_schedule_range_tool_handler,
    "academy_class_roster_range": _class_roster_range_tool_handler,
    "academy_consultation_schedule_range": _consultation_schedule_range_tool_handler,
    "academy_student_attendance_range": _student_attendance_range_tool_handler,
    "academy_student_attendance_calendar_image": _student_attendance_calendar_image_tool_handler,
    "academy_attendance_day": _attendance_day_tool_handler,
    "academy_staff_attendance_day": _staff_attendance_day_tool_handler,
    "academy_staff_attendance_range": _staff_attendance_range_tool_handler,
    "academy_staff_schedule_day": _staff_schedule_day_tool_handler,
    "academy_plan_by_date": _plan_by_date_tool_handler,
    "academy_assignment_by_date": _assignment_by_date_tool_handler,
    "academy_consultation_candidates": _consultation_candidates_tool_handler,
    "academy_consultation_note_save": _consultation_note_save_tool_handler,
    "academy_student_summary": _student_summary_tool_handler,
    "academy_student_card_image": _student_card_image_tool_handler,
    "academy_student_context": _student_context_tool_handler,
    "academy_student_record_cohort_latest": _student_record_cohort_tool_handler,
    "academy_student_record_lookup": _student_record_lookup_tool_handler,
    "academy_student_record_chart_image": _student_record_chart_image_tool_handler,
    "academy_monthly_test_records": _monthly_test_records_tool_handler,
    "academy_thread_roster_lookup": _thread_roster_lookup_tool_handler,
    "academy_set_brand_logo": _academy_set_brand_logo_tool_handler,
    "academy_reset_brand_logo": _academy_reset_brand_logo_tool_handler,
}

TOOL_CONTRACTS: dict[str, dict[str, Any]] = {
    "academy_schedule_range": {
        "purpose": "학원 행사/이벤트(academy_events) 조회 — 맥스컵, 월말 테스트, 휴일, 업무일정. 학생 출석/등원과는 무관",
        "args": ["start_date", "end_date"],
    },
    "academy_class_roster_range": {
        "purpose": "특정 날짜(오늘뿐 아니라 이번주/다음주 등 미래 날짜 포함)에 출석·등원 '예정'인, 수업에 배정된 학생 명단(이름/학교/학년) 조회. '출석해야 할 / 나와야 할 / 등원 예정 / 수업 있는' 학생 명단은 날짜와 무관하게 반드시 이 도구. class_schedules 기반 — 아직 출결을 체크하기 전의 '예정자' 명단이다 (실제 출결 기록이 아님).",
        "args": ["start_date", "end_date", "with_roster"],
        "aliases": ["오늘 출석할 학생", "출석해야 할 학생", "나와야 할 학생", "이번주 금요일 출석할 학생", "등원 예정 학생", "수업 명단", "수업별 학생"],
    },
    "academy_consultation_schedule_range": {
        "purpose": "신규 상담, 상담 일정, 체험수업, 무료체험, trial lesson 일정 조회",
        "args": ["start_date", "end_date", "new_registration_only", "trial_only"],
        "aliases": ["체험수업", "무료체험", "체험상담", "trial", "trial lesson"],
    },
    "academy_student_attendance_range": {
        "purpose": "특정 학생의 기간별 출석, 지각, 결석, 미체크 조회",
        "args": ["student_query", "start_date", "end_date", "today"],
    },
    "academy_student_attendance_calendar_image": {
        "purpose": "특정 학생의 출석을 달력 PNG 이미지로 생성. 날짜별 긴 출석 목록, 달력, 이미지 요청에 사용",
        "args": ["student_query", "start_date", "end_date", "today"],
    },
    "academy_attendance_day": {"purpose": "특정 날짜 학생 전체의 '이미 체크된' 실제 출결 현황/명단(출석/지각/결석/미체크) 조회 + PNG. 과거·오늘의 출결 '기록' 전용이다. 미래 날짜는 아직 출결 기록이 없어 전원 '미체크 0'으로 나오므로, '출석해야 할 예정 명단'에는 절대 쓰지 말고 academy_class_roster_range를 써라.", "args": ["date", "image"]},
    "academy_staff_attendance_day": {
        "purpose": "이미 출근한 강사, 출근 기록, 어제/과거 출근자 조회",
        "args": ["date"],
    },
    "academy_staff_attendance_range": {
        "purpose": "특정 강사의 기간별 출근 기록, 월간 출근 횟수, 지난주/이번달 출근일 조회",
        "args": ["staff_query", "start_date", "end_date"],
    },
    "academy_staff_schedule_day": {
        "purpose": "출근 예정 강사, 앞으로 출근해야 할 강사, 배정된 강사 조회",
        "args": ["date", "time_slot", "include_owner"],
    },
    "academy_plan_by_date": {
        "purpose": "날짜별 또는 강사별 운동계획서, 운동 목록, 완료 여부 조회",
        "args": ["date", "trainer_query", "time_slot"],
    },
    "academy_assignment_by_date": {"purpose": "날짜별 반배치와 담당 강사 조회", "args": ["date", "time_slot"]},
    "academy_consultation_candidates": {
        "purpose": "재원생 중 상담이 필요한 학생 후보 추천과 PNG 이미지 생성. 최근 2주 출결과 최근 5개 실기기록 추세를 서버 API로 조회",
        "args": ["today", "period_days", "limit"],
    },
    "academy_consultation_note_save": {
        "purpose": "특정 학생 상담 기록 저장. 사용자가 상담 내용, 팔로업, 등원 사유 등을 기록해달라고 할 때 사용",
        "args": ["student_query", "note", "consulted_at"],
    },
    "academy_student_summary": {"purpose": "학생 요약 텍스트 조회. 카드/이미지/파일 전달 요청에는 쓰지 않음", "args": ["student_query", "today", "period_days"]},
    "academy_student_card_image": {"purpose": "학생관리카드, 학생 카드, 카드 이미지를 PNG로 생성", "args": ["student_query", "today", "period_days"]},
    "academy_student_context": {
        "purpose": (
            "특정 학생의 수업 요일, 시간대, 최근 출석 요일, PACA/Peak ID 매핑, "
            "최근 기록 컨텍스트 조회. 학생 후속 질문이나 모호한 읽기 질문에 우선 사용"
        ),
        "args": ["student_query", "today", "period_days"],
    },
    "academy_student_record_cohort_latest": {
        "purpose": "PACA 재원생 기준 Peak 최신 실기 기록 집계. 재원생 기준 최신기록, 남녀 평균, 순위, 기록 명단 요청에 사용. 월말테스트/정기평가 참가자 집계가 아니라 실제 현재 재원생의 최신 기록이다.",
        "args": ["event_query", "limit"],
    },
    "academy_student_record_lookup": {
        "purpose": "특정 학생의 Peak 실기, 측정, 종목별 기록 조회. MAX 운동분석 변인, 퍼포먼스 분석 리포트, 운동처방 요청은 sports_max_analysis_variables가 우선이며 최근 기록도 함께 필요할 때만 같이 사용",
        "args": ["student_query", "event_query", "date", "today", "period_days"],
    },
    "academy_student_record_chart_image": {
        "purpose": "특정 학생의 Peak 실기, 측정, 종목별 최근 기록을 종목별 그래프 PNG 이미지로 생성",
        "args": ["student_query", "event_query", "today", "period_days", "limit"],
    },
    "academy_monthly_test_records": {"purpose": "월별 또는 정기 실기 평가 참가자 기준 종목 평균, 순위, 학교 제외 집계 조회. 일반 최신 학생 기록이 아니라 평가 참가자 집계를 원할 때 사용", "args": ["event_query", "test_id", "test_month", "exclude_schools", "today"]},
    "academy_thread_roster_lookup": {
        "purpose": (
            "현재 Discord 스레드 작업파일(work/*.md)에 저장된 반 편성표/명단 조회. "
            "사용자가 '스레드에 저장해둔 명단', '방금 추가한 반 명단', '정시반/학교반 편성표 명단'을 묻는 경우 "
            "학원 DB나 날짜별 수업 배정 조회보다 이 도구를 먼저 사용한다."
        ),
        "args": ["roster_names"],
    },
    "academy_set_brand_logo": {
        "purpose": "사용자가 이미지를 첨부하고 학원 로고를 그 이미지로 바꿔/교체/설정해달라고 할 때 사용. 첨부 이미지를 학원 로고로 저장해 리포트/카드 스탬프에 적용. 인자 없음",
        "args": [],
        "aliases": ["로고 바꿔", "로고 교체", "로고 이걸로", "로고 설정", "스탬프 바꿔"],
    },
    "academy_reset_brand_logo": {
        "purpose": "학원 로고를 기본/원래대로 되돌리거나 삭제해달라고 할 때 사용. 저장된 학원 로고를 지워 기본 스탬프로 복원. 인자 없음",
        "args": [],
        "aliases": ["로고 기본", "로고 원래대로", "로고 삭제", "로고 초기화"],
    },
}
