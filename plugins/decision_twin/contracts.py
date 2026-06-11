"""Tool contracts shown to the LLM decision twin."""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)


_CORE_CONTRACTS: dict[str, dict[str, Any]] = {
    "life_record_ingest_pdf": {
        "domain": "life_record",
        "purpose": "첨부된 한국 생기부/PDF/MHTML/MHT를 원본 기준 DB로 저장하고 검증한다.",
        "requires": ["supported local attachment path"],
    },
    "life_record_summary": {
        "domain": "life_record",
        "purpose": "현재 스레드 생기부 DB를 요약한다. 생기부 원문 조회 없이 답하지 않는다.",
        "requires": ["existing life-record DB in thread"],
    },
    "life_record_lookup": {
        "domain": "life_record",
        "purpose": "학생 생기부 DB에서 학년/학기/영역별 원문 근거를 조회한다.",
        "requires": ["student or current thread context"],
    },
    "life_record_search": {
        "domain": "life_record",
        "purpose": "생기부 DB에서 키워드/영역 기반 원문 근거를 검색한다.",
        "requires": ["query"],
    },
    "life_record_verify": {
        "domain": "life_record",
        "purpose": "저장된 생기부 추출값과 검수 상태를 확인한다.",
        "requires": ["document_id when known"],
    },
    "youtube_analyze_video": {
        "domain": "youtube_ops",
        "purpose": "유튜브 URL/영상 ID를 transcript 기반으로 분석하고 필요하면 이미지 카드를 만든다.",
        "requires": ["youtube url or video id"],
    },
    "academy_hakjong_report_package": {
        "domain": "academy_ops",
        "purpose": "잠긴 premium_hakjong_report PDF/HTML을 검증하고 통과한 PDF만 MEDIA로 전달한다.",
        "requires": ["html_path", "pdf_path", "student_name", "evidence_tools"],
    },
    "academy_render_image": {
        "domain": "academy_ops",
        "purpose": "학원 데이터/리포트/표를 Discord 전달용 PNG로 렌더링한다.",
        "requires": ["safe html body"],
    },
    "academy_report_image": {
        "domain": "academy_ops",
        "purpose": "고정된 표 형식의 학원 리포트를 PNG로 렌더링한다.",
        "requires": ["columns", "rows"],
    },
    "media_delivery_contract": {
        "domain": "gateway_media",
        "purpose": "이미 생성된 로컬 파일은 MEDIA:<absolute_path> 형식으로 답해야 플랫폼이 파일로 전달한다.",
        "requires": ["file under Miho media cache or allowed media dir"],
    },
}


def decision_tool_contracts() -> dict[str, dict[str, Any]]:
    """Return compact, model-facing contracts for cross-domain routing."""
    contracts = dict(_CORE_CONTRACTS)
    try:
        from plugins.academy_ops.tool_registry import TOOL_CONTRACTS

        for name, contract in TOOL_CONTRACTS.items():
            contracts.setdefault(
                name,
                {
                    "domain": "academy_ops",
                    "purpose": str(contract.get("purpose") or ""),
                    "args": list(contract.get("args") or []),
                },
            )
    except Exception as exc:
        logger.debug("decision twin academy contracts unavailable: %s", exc)
    return contracts
