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
        "purpose": (
            "학생 생기부 DB에서 학년/학기/영역별 원문 근거를 조회한다. "
            "학종 리포트 근거 확인에는 정시엔진이 아니라 이 생기부 조회 계열을 우선한다. "
            "다만 학종이 아닌 수시 교과/실기 환산점수, 전년도 컷, 상향/중립/안전 추천은 "
            "생기부 조회만으로 잠그지 말고 수시 점수 산출 흐름과 대학 공식 자료를 함께 써야 한다."
        ),
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
        "purpose": (
            "내용 JSON만 주면 껍데기(로고/푸터/브랜딩)는 고정 템플릿이 보장한다. "
            "학교별 학종 패키지(susi27_rule_lookup)와 생기부(life_record_lookup/search/summary)를 "
            "근거로 섹션 내용을 작성하라. "
            "검증 통과한 PDF만 ~/.miho/media_cache/susi_student_record/validated 로 승격하고 "
            "media_tag를 반환한다."
        ),
        "requires": ["student_name", "student_stage", "evidence_tools", "content"],
    },
    "academy_render_image": {
        "domain": "academy_ops",
        "purpose": (
            "학원 데이터/리포트/표를 Discord 전달용 PNG로 렌더링한다. "
            "전용 이미지 도구가 정확히 맞지 않을 때만 HTML 기반으로 사용한다."
        ),
        "requires": ["safe html body"],
    },
    "academy_report_image": {
        "domain": "academy_ops",
        "purpose": (
            "고정된 표 형식의 학원 리포트를 PNG로 렌더링한다. "
            "열과 행이 명확한 표/기록표/명단형 자료에만 사용한다."
        ),
        "requires": ["columns", "rows"],
    },
    "jungsi_login": {
        "domain": "jungsi_excel_importer",
        "purpose": (
            "정시엔진 전용 로그인 링크를 발급한다. "
            "학종/생기부/수시 리포트 요청에는 사용하지 않는다."
        ),
        "requires": ["authorized Discord user needing jungsi-engine account connection"],
    },
    "jungsi_student_university_score": {
        "domain": "jungsi_excel_importer",
        "purpose": (
            "실기/수시 추천 작업 순서: "
            "①학생 성적 확보(life_record_lookup 또는 사용자 제공) "
            "②후보 학교 룰 조회(susi27_rule_lookup — 학종 패키지·실기 종목·반영식·전년도 결과 포함) "
            "③환산점수 계산(susi27_score_calculate 또는 jungsi_student_university_score) "
            "④전년도 결과(admission_result_26_json)와 비교 "
            "⑤상향/적정 분류 + 왜 되는지/안 되는지 근거 서술. "
            "점수 없이 추천을 확정하지 말 것. 모든 후보에 환산점수·전년도 수치를 병기할 것."
        ),
        "requires": ["student_query", "university or department candidates"],
    },
    "send_message": {
        "domain": "messaging",
        "purpose": (
            "Discord 등 현재 플랫폼 채널에 최종 텍스트 응답을 전송한다. "
            "파일 전달이나 도메인 분석 도구를 대체하지 않는다."
        ),
        "requires": ["target channel and response text"],
    },
    "media_delivery_contract": {
        "domain": "gateway_media",
        "purpose": (
            "이미 생성된 로컬 파일은 MEDIA:<absolute_path> 형식으로 답해야 플랫폼이 파일로 전달한다. "
            "파일 재전달/첨부 요청을 정시엔진 로그인 링크나 계정 연결 안내로 대체하지 않는다."
        ),
        "requires": ["file under Miho media cache or allowed media dir"],
    },
}


def decision_tool_contracts() -> dict[str, dict[str, Any]]:
    """Return compact, model-facing contracts for cross-domain routing."""
    contracts = _registered_tool_contracts()
    contracts.update(_CORE_CONTRACTS)
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


def _registered_tool_contracts() -> dict[str, dict[str, Any]]:
    try:
        from tools.registry import registry
    except ImportError as exc:
        logger.debug("decision twin registry contracts unavailable: %s", exc)
        return {}

    contracts: dict[str, dict[str, Any]] = {}
    for name in registry.get_all_tool_names():
        entry = registry.get_entry(name)
        if entry is None:
            continue
        schema = entry.schema if isinstance(entry.schema, dict) else {}
        contracts[name] = {
            "domain": entry.toolset,
            "purpose": _purpose(entry.description, schema, name, entry.toolset),
            "args": _schema_args(schema),
        }
    return contracts


def _purpose(description: str, schema: dict[str, Any], name: str, toolset: str) -> str:
    text = str(description or schema.get("description") or "").strip()
    if not text:
        text = f"Registered Miho tool {name} in toolset {toolset}."
    return _compact(text)


def _schema_args(schema: dict[str, Any]) -> list[str]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return []
    return [str(name) for name in properties.keys()]


def _compact(value: str, limit: int = 360) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
