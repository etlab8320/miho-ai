"""Constants for Governance OS final delivery detection."""

from __future__ import annotations

import re

PLAYBOOK_BY_TOOL = {
    "academy_hakjong_report_package": "academy_hakjong_report",
    "academy_practical_reco_package": "academy_practical_recommendation",
    "academy_practical_reco_all_candidates": "academy_practical_recommendation",
    "susi27_recommend_candidates": "academy_practical_recommendation",
    "susi27_score_calculate": "susi_score_calculation",
    "life_record_ingest_pdf": "life_record_ingest",
    "life_record_verify": "life_record_ingest",
    "html_pdf_quality_gate": "designed_pdf_artifact",
    "media_delivery_contract": "discord_attachment_delivery",
}
# 미호는 범용 거버넌스 OS다. leak 마커는 *거버넌스 내부에서만* 쓰는 고유 구절로만
# 한정해, 일반 질문·코딩·대화 답변을 절대 오탐 차단하지 않는다.
# (예: "npm run build를 다시 실행해야 합니다", "next_action 필드를 추가" 같은 정상
#  기술 답변은 여기에 걸리면 안 된다.)
INTERNAL_GUARD_LEAK_MARKERS = (
    "확인 근거가 충분하지 않아",
    "그대로 전달하지 않겠습니다",
    "필요한 확인을 다시 거쳐 이어서",
    "결과를 전달하지 말고",
    "전달하지 말고 같은",
    "전달하지 말고 후검증",
    "후검증을 통과한 뒤",
    "후검증을 통과하지 못",
    "후검증 통과 기록",
    "후검증이 결과 전달을 막",
    "후검증을 다시 실행",
    "후검증 대상 결과를 읽을 수 없",
    "후검증 정보가 없습니다",
    "후검증 담당이 요청된 작업과",
    "전용 도구를 다시 실행",
    "전용 도구로 다시 실행",
    "전용 도구를 사용하고, 결과는",
    "등록된 전용 도구를 사용",
    "의미 검증을 완료하지 못",
    "올바른 검수 도구로 다시",
    "전달하기 전에 후검증을 통과",
)
# 거버넌스 내부 JSON이 통째로 새는 경우만 잡는다. 일반 API 필드명 단독("next_action"
# 하나만 언급)으로는 절대 차단하지 않는다 — 거버넌스 고유 키이거나, 거버넌스 전용
# 키-값 조합이 함께 나타날 때만 leak으로 판정한다.
GOVERNANCE_JSON_LEAK_KEYS = (
    "retry_instruction_ko",
    "review_evidence_missing",
)
GOVERNANCE_JSON_LEAK_PAIRS = (
    ("next_action", "retry_required"),
    ("next_action", "retry_needed"),
    ("governance_review", "retry_tools"),
)
GOVERNANCE_REVIEW_MARKERS = (
    "governance os",
    "final delivery gate",
    "delivery gate",
    "dispatcher",
    "playbook",
    "auxiliary dispatcher",
    "auxiliary reviewer",
    "readiness",
    "preflight",
    "governance_pre_tool_call",
    "governance_transform_llm_output",
    "적대적 리뷰",
    "개발 리뷰",
    "코드 리뷰",
    "리뷰 문서",
    "오탐",
    "후보 제한",
    "보조 라우터",
    "보조 리뷰어",
    "라우팅",
    "게이트",
)
SCORE_CLAIM_RE = re.compile(
    r"(수시|환산|내신|등급|점수)[^\n.。]{0,40}\d+(?:\.\d+)?\s*점"
    r"|\d+(?:\.\d+)?\s*점[^\n.。]{0,40}(수시|환산|내신|등급|점수)"
)
STUDENT_SCORE_CLAIM_RE = re.compile(
    r"(학생|지원자|수험생|서연|가은|가능권|합격|전형|대학|추천)"
    r"[^\n.。]{0,80}\d+(?:\.\d+)?\s*점"
    r"|\d+(?:\.\d+)?\s*점[^\n.。]{0,80}"
    r"(학생|지원자|수험생|서연|가은|가능권|합격|전형|대학|추천)"
)
FINAL_CLAIM_MARKERS = (
    "완료했습니다",
    "만들었습니다",
    "생성했습니다",
    "첨부했습니다",
    "보냈습니다",
    "전달합니다",
    "저장했습니다",
    "추천합니다",
    "가능권입니다",
    "현실적입니다",
    "적정입니다",
    "안정입니다",
    "상향입니다",
)
COMPLETION_CLAIM_MARKERS = (
    "완료했습니다",
    "만들었습니다",
    "생성했습니다",
    "첨부했습니다",
    "보냈습니다",
    "전달합니다",
    "저장했습니다",
)
DOMAIN_VERDICT_MARKERS = (
    "추천합니다",
    "가능권입니다",
    "현실적입니다",
    "적정입니다",
    "안정입니다",
    "상향입니다",
)
DOMAIN_DELIVERY_TERMS = (
    "학생",
    "지원자",
    "수험생",
    "서연",
    "가은",
    "대학",
    "학교",
    "전형",
    "수시",
    "실기",
    "학종",
    "생기부",
    "학생부",
    "리포트",
    "pdf",
    "환산",
    "점수",
    "내신",
    "등급",
    "지원 가능",
)
META_EXPLANATION_TERMS = (
    "도구",
    "서브에이전트",
    "subagent",
    "reviewer",
    "리뷰어",
    "시스템",
    "구조",
    "게이트",
    "라우팅",
    "방식",
    "설정",
    "권한",
    "제한",
)
PERSONALIZED_DELIVERY_TERMS = (
    "학생",
    "지원자",
    "수험생",
    "서연",
    "가은",
    "점수",
    "가능권",
    "합격",
    "전형",
    "대학",
    "학교",
)
ARTIFACT_COMPLETION_TERMS = (
    "pdf 생성",
    "리포트 생성",
    "첨부 완료",
    "저장했습니다",
    "보냈습니다",
    "전달합니다",
    "생성했습니다",
)
