"""2027 수시엔진 rule lookup and calculation helpers."""

from __future__ import annotations

from typing import Any

from .service import lookup_rules, calculate_score


def _lookup_handler(args: dict[str, Any]) -> dict[str, Any]:
    return lookup_rules(
        university=args.get("university"),
        department=args.get("department"),
        admission_track=args.get("admission_track"),
        limit=int(args.get("limit") or 20),
    )


def _calculate_handler(args: dict[str, Any]) -> dict[str, Any]:
    return calculate_score(
        university_id=str(args.get("university_id") or ""),
        grades=args.get("grades") or [],
        attendance=args.get("attendance") or {},
        practical_records=args.get("practical_records") or {},
    )


def register(ctx: Any) -> None:
    ctx.register_tool(
        name="susi27_rule_lookup",
        toolset="susi_ops",
        schema={
            "type": "object",
            "properties": {
                "university": {"type": "string", "description": "대학명 일부 또는 전체."},
                "department": {"type": "string", "description": "학과/모집단위명 일부."},
                "admission_track": {"type": "string", "description": "전형명 일부. 예: 일반, 농어촌, 사배자."},
                "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            },
            "additionalProperties": False,
        },
        handler=_lookup_handler,
        description=(
            "학교별 수시 패키지 조회 — 학종 리포트와 실기/수시 추천 체인의 룰 조회 단계에서 사용한다. "
            "반환 rows에는 전형 구조(admission_meta: 단계별 반영비율·모집인원·수능최저·전년도 cut_data), "
            "전년도 결과(admission_result_26), 지원자격(eligibility), 모집단위 매칭(school_info), "
            "교과 반영식(score_logic), 출결 반영(attendance_logic), 실기 종목(practical_events), "
            "맥스 예상컷(db_snapshot.max_expected_cut)이 포함된다. "
            "학종 리포트 체인: 이 도구로 해당 학교가 무엇을 중요하게 보는지 확인한 뒤 내용을 작성해 "
            "academy_hakjong_report_package로 넘긴다. "
            "실기/수시 추천 체인: 이 도구의 score_logic을 susi27_score_calculate에 넘겨 환산하고 "
            "admission_result_26·cut_data와 비교해 상향/적정을 판단한다. "
            "실기전형 추천은 환산점수 숫자+실기 종목+전년도 결과로만 판단 — 등급 나열로 대체하지 말고, "
            "생기부 세특/서사/학종 언어는 넣지 말 것 (학종 리포트 전용). "
            "정시엔진 U_ID 기반 요약이 필요할 때만 jungsi_rule_summary를 대신 사용한다 (둘 다 호출하지 말 것)."
        ),
    )
    ctx.register_tool(
        name="susi27_score_calculate",
        toolset="susi_ops",
        schema={
            "type": "object",
            "properties": {
                "university_id": {"type": "string", "description": "27susi.대학정보 대학ID."},
                "grades": {"type": "array", "items": {"type": "object"}, "description": "학생 교과 성적 rows."},
                "attendance": {"type": "object", "description": "출결 정보."},
                "practical_records": {"type": "object", "description": "실기 종목별 기록."},
            },
            "required": ["university_id"],
            "additionalProperties": False,
        },
        handler=_calculate_handler,
        description=(
            "검증(verified)된 수시 룰로 학생 교과 성적을 환산점수로 계산한다. "
            "university_id와 grades는 susi27_rule_lookup 결과와 life_record_lookup 성적에서 가져온다. "
            "unverified/missing 룰은 추측하지 않고 거부한다 — 그 경우 점수 없이 추천을 확정하지 말 것."
        ),
    )
