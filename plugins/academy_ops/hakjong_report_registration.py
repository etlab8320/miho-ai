"""Tool registration contract for hakjong report package generation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def register_hakjong_report_tool(ctx: Any, handler: Callable[..., str]) -> None:
    ctx.register_tool(
        name="academy_hakjong_report_package",
        toolset="academy_ops",
        schema={
            "type": "object",
            "properties": {
                "student_name": {"type": "string", "description": "학생명. PDF 표지와 본문에 삽입된다."},
                "student_stage": {
                    "type": "string",
                    "description": (
                        "학생 상태. grade1/grade2/grade3/graduate 또는 고1/고2/고3/N수생. "
                        "리포트의 목적이 단계마다 다르다 — ①고3(세특 채워짐)·N수생: 평가형. "
                        "②고3(당해 세특 미입력): 이전 생기부 기반 가능성+gap_plan. "
                        "③고1 2학기·고2: 방향성 설계형. ④고1 1학기: 상담 기반 시작 설계. "
                        "세특 유무는 도구가 DB로 검증하니 단계를 추측하지 말 것."
                    ),
                },
                "evidence_tools": {
                    "type": "array",
                    "description": (
                        "실제 근거 조회에 사용한 도구/소스 이름. 3학년/N수생은 life_record_* 계열이 "
                        "필수이고, 모든 학종 PDF는 hakjong_storm_prewrite를 필수로 포함한다."
                    ),
                    "items": {"type": "string"},
                },
                "content": {
                    "type": "object",
                    "description": (
                        "리포트 내용 JSON. 리포트 1부 = (학생, 대학, 전형) 1조합 — 여러 학교 추천이면 "
                        "학교마다 따로 호출한다. 필수 키: student{name} · university{name, department, "
                        "college, track} · badge{grade, action} · title_lines[] · cover{pills[], "
                        "key_judgment, metrics[]} · track_section{heading, info_cards[], rows[], "
                        "strong_points, caution_points, footnote} · diagnosis_section{heading, "
                        "strength, risk, rows[], gauges[], footnote} · strategy_section{heading, "
                        "actions[], interview_rows[], final_judgment, checklist, footnote, gap_plan}. "
                        "gap_plan은 재학생 필수이며 분야별 1페이지 상세 세특 설계로 렌더된다. "
                        "분야는 이 학생 세특에 전공 관련 탐구가 실제로 있는 과목만 잡고, "
                        "steps는 3개 이상이며 분야 본문 500자 이상을 채운다. 수치와 전형 구조는 "
                        "susi27_rule_lookup 및 생기부 성적의 실제 값만 쓴다. 로고·푸터·브랜딩은 "
                        "템플릿이 보장하므로 content에 넣지 않는다."
                    ),
                },
            },
            "required": ["student_name", "student_stage", "evidence_tools", "content"],
            "additionalProperties": False,
        },
        handler=handler,
        description=(
            "너는 입시 상담사다. 이 리포트는 일반 조언 출력기가 아니라 이 학생 한 명을 위한 맞춤 상담이다 — "
            "학생마다 답이 같으면 있으나 마나다. 작성 순서: ①학생 분석 — life_record_lookup/search/summary로 "
            "세특 전문을 한 문항씩 끝까지 정독한다. 한 세특 안에도 활동이 여러 개고 진짜 알맹이는 "
            "뒷부분에 있을 수 있다. 과목명·앞 문장 같은 표면이 아니라 전공에 닿는 구체 활동을 끝까지 읽어 "
            "발굴하라 → ②학교/학과 분석(hakjong_qualitative_profile로 평가축·그 학과가 원하는 세특 방향) → "
            "③강점 살리기(학생의 어느 실제 기록이 학과 어느 평가요소에 먹히는지 1:1로 짚는다) → "
            "④약점 보완(학과 방향에 학생 기록이 닿아 있으면 디벨롭하고, 없으면 그 분야에서 새 세특을 설계) → "
            "⑤학교에 맞춘다. 세특 조언은 분야 단위로 하되 이미 기록을 가진 과목만 그 과목에서 디벨롭한다. "
            "내용 JSON만 주면 껍데기(로고/푸터/브랜딩)는 고정 템플릿이 보장한다. "
            "학교별 학종 패키지와 생기부를 근거로 섹션 내용을 작성하라. 톤은 학원 선생님이 학생과 학부모 앞에서 "
            "상담하며 설명하는 자연스러운 말투다. AI 티 나는 추상 표현, 내부 판단 과정, 배제 설명, "
            "검증 톤은 본문에 노출하지 않는다. 내용 깊이: 추상 조언은 금지이고, 학생의 실제 과목·성적·기록을 "
            "hakjong_qualitative_profile과 연결해 무엇을 어떤 방법으로 할지까지 구체적으로 쓴다. "
            "고1·2·고3·N수생 단계별 목적을 다르게 적용하고, N수생은 gap_plan을 넣지 않는다. "
            "단계는 도구가 생기부 생년으로 자동 판정한다. terminal/write_file/execute_code로 HTML/PDF를 직접 만들지 마라 — "
            "정식본은 academy_hakjong_report_package가 생성한 manifest_version=2, schema/pdf checks 포함 파일뿐이다. "
            "반려(ok=false)는 사용자에게 실패 보고로 끝내지 말고, errors를 수정 지시로 읽어 같은 턴에서 content를 "
            "보강해 재호출한다. 검증 통과한 PDF만 ~/.miho/media_cache/susi_student_record/validated 로 승격하고 "
            "media_tag를 반환한다."
        ),
    )
