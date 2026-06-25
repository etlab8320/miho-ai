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
    "media_delivery_contract": "discord_attachment_delivery",
}
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
