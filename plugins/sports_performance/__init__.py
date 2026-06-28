"""Sports performance coaching plugin."""

from __future__ import annotations

from typing import Any

from .feedback_tool import make_feedback_tool_handler, schema_tool_handler
from .max_analysis_api import max_analysis_variables_tool_handler
from .motion_analysis import provider_status_payload, video_analysis_tool_handler
from .pe_brain_evidence import pe_brain_evidence_tool_handler
from .report_html import sports_report_html_tool_handler
from .report_package import make_report_package_tool_handler
from .report_templates import report_template_tool_handler
from .result_reviewer import make_result_review_hook


COACH_INSTRUCTIONS = (
    "체대입시 운동분석 코치다. 업체 API/PDF에서 온 각도·접지·안정성 지표를 "
    "종목별 체크포인트로 해석하되, 논문팩이 없는 항목은 근거 대기 상태로 표시한다. "
    "통증 신호가 있으면 고강도 처방보다 현장 확인과 안전 조치를 우선한다."
)
REVIEWER_INSTRUCTIONS = (
    "체대입시 운동 피드백 reviewer다. 학생/종목/지표, 기술 피드백 구조, "
    "안전 문구, 논문 근거 연결 상태를 검수하고 위험하면 전달을 막는다."
)


def register(ctx: Any) -> None:
    llm = getattr(ctx, "llm", None)
    ctx.register_hook("transform_tool_result", make_result_review_hook(llm))
    ctx.register_auxiliary_task(
        key="sports_performance_coach",
        display_name="Sports performance coach",
        description="체대입시 종목별 운동분석 지표를 훈련 피드백으로 바꾸는 코치 에이전트",
        defaults={"provider": "auto", "timeout": 120, "instructions": COACH_INSTRUCTIONS},
    )
    ctx.register_auxiliary_task(
        key="sports_performance_reviewer",
        display_name="Sports performance reviewer",
        description="운동 피드백의 안전성·근거·체대입시 적합성을 검수하는 reviewer",
        defaults={"provider": "auto", "timeout": 120, "instructions": REVIEWER_INSTRUCTIONS},
    )
    ctx.register_tool(
        name="sports_motion_report_package",
        toolset="sports_performance",
        schema={
            "type": "object",
            "properties": {
                "student_name": {"type": "string", "description": "학생명. 예: 강지연."},
                "student_query": {"type": "string", "description": "student_name 대체 검색어."},
                "exercise": {"type": "string", "description": "종목명. 예: 제멀."},
                "academy_id": {"type": "string", "description": "특정 교육원 UUID."},
                "academy_name": {"type": "string", "description": "교육원명 일부 검색. 예: 일산."},
                "from_date": {"type": "string", "description": "조회 시작일. YYYY-MM-DD."},
                "to_date": {"type": "string", "description": "조회 종료일. YYYY-MM-DD."},
                "evidence_refs": {"type": "array", "items": {"type": "string"}, "description": "검증된 논문/근거팩 ID."},
            },
            "required": ["student_name", "exercise"],
            "additionalProperties": False,
        },
        handler=make_report_package_tool_handler(llm),
        description=(
            "학생 운동퍼포먼스 분석 리포트를 MAX API 실제 변인 조회, sports_motion_feedback reviewer, "
            "HTML-first 리포트, PDF 품질 게이트까지 한 번에 생성한다. "
            "강지연 최근 기록으로 제멀 분석 리포트처럼 리포트/보고서/PDF 맥락이면 이 도구를 먼저 사용한다."
        ),
    )
    ctx.register_tool(
        name="sports_motion_schema",
        toolset="sports_performance",
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=schema_tool_handler,
        description="체대입시 운동분석 표준 스키마와 지원 종목/지표 alias를 반환한다.",
    )
    ctx.register_tool(
        name="sports_pe_brain_evidence",
        toolset="sports_performance",
        schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "search, sync, list 중 하나. 기본 search."},
                "exercise": {"type": "string", "description": "종목명. 예: 제멀, 메디, 왕복달리기."},
                "query": {"type": "string", "description": "논문 제목/요약 검색어."},
                "category": {"type": "string", "description": "physical 또는 mental."},
                "include_review_required": {
                    "type": "boolean",
                    "description": "true면 검토 필요 논문까지 보여준다. 기본 false.",
                },
                "limit": {"type": "integer", "description": "반환할 근거팩 수. 최대 20."},
                "refresh": {"type": "boolean", "description": "true면 PE-brain API에서 새로 동기화한다."},
            },
            "additionalProperties": False,
        },
        handler=pe_brain_evidence_tool_handler,
        description="PE-brain 논문을 체대입시 운동 피드백용 accepted evidence pack으로 검색/동기화한다.",
    )
    ctx.register_tool(
        name="sports_motion_feedback",
        toolset="sports_performance",
        schema={
            "type": "object",
            "properties": {
                "student_name": {"type": "string", "description": "학생명."},
                "student_query": {"type": "string", "description": "학생 검색명. student_name 대체 가능."},
                "exercise": {"type": "string", "description": "종목명. 예: 제멀, 메디, 왕복달리기."},
                "metrics": {"type": "object", "description": "업체 API/PDF에서 온 각도·시간·안정성 지표."},
                "records": {"type": "object", "description": "최근 기록/최고 기록 등 선택 입력."},
                "pain_flags": {"type": "array", "items": {"type": "string"}, "description": "통증/저림/불안정감."},
                "evidence_refs": {"type": "array", "items": {"type": "string"}, "description": "연결된 논문/근거팩 ID."},
                "source": {"type": "string", "description": "manual, vendor_api, parsed_pdf 등."},
                "measured_at": {"type": "string", "description": "측정일. YYYY-MM-DD 권장."},
            },
            "required": ["exercise", "metrics"],
            "additionalProperties": False,
        },
        handler=make_feedback_tool_handler(llm),
        description=(
            "업체 운동분석 API/PDF 파싱값을 학생별 체대입시 종목 피드백으로 바꾼다. "
            "제멀/메디신볼/왕복달리기/배근력/좌전굴을 지원한다. "
            "결과는 sports_performance_reviewer 검수 후 전달한다."
        ),
    )
    ctx.register_tool(
        name="sports_max_analysis_variables",
        toolset="sports_performance",
        schema={
            "type": "object",
            "properties": {
                "student_name": {"type": "string", "description": "운동분석 변인을 조회할 학생명. API 응답 후 학생명으로 필터링한다."},
                "student_query": {"type": "string", "description": "student_name 대체 검색어. 예: 강지연."},
                "academy_id": {"type": "string", "description": "특정 교육원 UUID. 없으면 전지점 조회."},
                "academy_name": {"type": "string", "description": "교육원명 일부 검색. 예: 일산, 강남."},
                "sport": {"type": "string", "description": "slj 또는 sprint. 제멀/제자리멀리뛰기는 slj로 넣는다."},
                "from_date": {"type": "string", "description": "시작일. YYYY-MM-DD."},
                "to_date": {"type": "string", "description": "종료일. YYYY-MM-DD."},
                "limit": {"type": "integer", "description": "페이지 크기. 최대 1000."},
                "offset": {"type": "integer", "description": "페이지 시작 위치."},
                "collect_all_pages": {"type": "boolean", "description": "true면 페이지를 반복 조회한다."},
                "max_pages": {"type": "integer", "description": "반복 조회 최대 페이지 수. 기본 20."},
                "timeout_seconds": {"type": "integer", "description": "외부 API 요청 제한 시간."},
            },
            "additionalProperties": False,
        },
        handler=max_analysis_variables_tool_handler,
        description=(
            "맥스체대입시 SLJ/SPRINT 운동분석 변인 API를 조회한다. "
            "학생의 제멀/스프린트 운동분석, 퍼포먼스 분석 리포트, 변인 기반 부족점, 운동처방 요청의 첫 단계로 사용한다. "
            "일반 Peak 실기 기록만 묻는 요청이 아니라 분석 변인/운동처방/리포트 맥락일 때 사용한다. "
            "맥락이 애매하면 academy_student_record_lookup의 Peak 최근 기록과 함께 조회해 더 맞는 근거를 비교한다. "
            "전지점, 특정 교육원, 학생명, 기간, 종목, 전체 페이지 수집을 지원한다."
        ),
    )
    ctx.register_tool(
        name="sports_report_template",
        toolset="sports_performance",
        schema={
            "type": "object",
            "properties": {
                "exercise": {"type": "string", "description": "종목명. 현재 제멀/제자리멀리뛰기 지원."},
            },
            "additionalProperties": False,
        },
        handler=report_template_tool_handler,
        description=(
            "운동분석 PDF 전 단계 템플릿을 반환한다. "
            "핵심 변인 설명, 상위권 비교 레이어, 처방 라이브러리, 레퍼런스 맵, PDF 섹션 계약을 포함한다."
        ),
    )
    ctx.register_tool(
        name="sports_report_html_template",
        toolset="sports_performance",
        schema={
            "type": "object",
            "properties": {
                "exercise": {"type": "string", "description": "종목명. 제멀/왕복달리기/메디신볼."},
                "student": {"type": "object", "description": "name, gender, academy, measured_at."},
                "record": {"type": "object", "description": "current, previous, change, percentile."},
                "variables": {"type": "array", "items": {"type": "object"}, "description": "변인별 측정/상위모델 비교값."},
                "max_analysis": {"type": "object", "description": "sports_max_analysis_variables 원본 응답. records에서 variable_value를 읽는다."},
                "feedback": {"type": "object", "description": "sports_motion_feedback 결과. reviewer.status=pass 필요."},
                "comparison": {"type": "array", "items": {"type": "object"}, "description": "전국 성별 상위 1%·5% 비교 요약."},
                "bottlenecks": {"type": "array", "items": {"type": "object"}, "description": "우선 개선점 3개."},
                "mode": {"type": "string", "description": "template_preview일 때만 측정 대기 placeholder 허용."},
                "allow_placeholders": {"type": "boolean", "description": "템플릿 미리보기 전용. 실제 학생 리포트에서는 false."},
            },
            "additionalProperties": False,
        },
        handler=sports_report_html_tool_handler,
        description=(
            "운동분석 리포트용 HTML-first PDF 중간 HTML을 생성한다. "
            "실제 학생 리포트는 sports_max_analysis_variables의 variable_value와 "
            "sports_motion_feedback reviewer pass 결과를 받은 뒤에만 호출한다. "
            "HTML은 첨부하지 말고 html_pdf_quality_gate로 PDF 변환/검증 후 전달한다. "
            "MAX 로고, 변인 점수표, 전국 성별 상위 모델 비교, 다변인 운동처방, 논문 근거, LLM 후검증 섹션을 포함한다."
        ),
    )
    ctx.register_tool(
        name="sports_video_analyze",
        toolset="sports_performance",
        schema={
            "type": "object",
            "properties": {
                "student_name": {"type": "string", "description": "학생명."},
                "student_query": {"type": "string", "description": "학생 검색명. student_name 대체 가능."},
                "exercise": {"type": "string", "description": "종목명. 예: 제멀, 좌전굴, 메디신볼."},
                "video_path": {"type": "string", "description": "업로드/저장된 영상 파일 경로."},
                "provider": {
                    "type": "string",
                    "description": "auto, sports2d, sports2d_2d, rtmpose, mmpose 중 하나. 기본 auto.",
                },
                "camera_view": {"type": "string", "description": "side, front, back 등 촬영 방향."},
                "visible_side": {"type": "string", "description": "Sports2D visible_side override."},
                "output_dir": {"type": "string", "description": "분석 결과 저장 디렉터리."},
                "time_range": {
                    "type": "array",
                    "items": {"type": "number"},
                    "minItems": 2,
                    "maxItems": 2,
                    "description": "분석 구간 [start_seconds, end_seconds].",
                },
                "pose_model": {"type": "string", "description": "Sports2D pose_model. 기본 body_with_feet."},
                "mode": {"type": "string", "description": "Sports2D mode. lightweight, balanced, performance."},
                "execute": {"type": "boolean", "description": "true면 실제 Sports2D CLI를 실행한다. 기본 false."},
                "timeout_seconds": {"type": "integer", "description": "실행 제한 시간. 기본 900초."},
            },
            "required": ["exercise", "video_path"],
            "additionalProperties": False,
        },
        handler=video_analysis_tool_handler,
        description=(
            "단일카메라 체대입시 영상을 무료 오픈소스 provider로 분석 준비/실행한다. "
            f"provider 상태는 {provider_status_payload()['recommended_default']}를 기본으로 한다. "
            "Sports2D+RTMPose 2D 계약과 단일카메라 한계를 결과에 포함한다."
        ),
    )
