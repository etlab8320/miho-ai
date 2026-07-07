"""Tool contracts shown to the LLM decision twin."""

from __future__ import annotations

import logging
from typing import Any

from .contract_schema import normalize_tool_contract


logger = logging.getLogger(__name__)
_DISCOVERY_ATTEMPTED = False


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
    "academy_practical_reco_package": {
        "domain": "academy_ops",
        "purpose": (
            "수시 실기전형 추천·내신환산 산출물(표/재계산표/리포트 무엇이든)은 반드시 이 도구로 만든다 — "
            "academy_render_image/academy_report_image로 표를 직접 그리지 말 것(로고·푸터 누락, 메타 노출, A4 잘림 발생). "
            "사용자가 추천 개수를 지정했거나 상담용 핵심 추천 최대 8개를 원할 때 고정 템플릿 PDF로 만든다. "
            "추천 후보·환산점수·전년도 수치는 susi27_recommend_candidates 단일 파이프라인 결과값만 사용. "
            "susi27_rule_lookup/susi27_score_calculate를 손으로 조립해 추천 목록을 만들지 말 것. "
            "사용자가 개수를 지정하지 않고 '지역 안 가능한 학교 전부/전체'를 원하면 "
            "academy_practical_reco_all_candidates를 사용한다. "
            "상향은 (내신환산+실기만점) ≥ 전년도 최종합 학교만 — 만점으로도 못 닿는 학교는 절대 싣지 않는다. "
            "선별 과정은 리포트에 쓰지 않는다: 제외 학교·검토 수·과정 설명 금지, 추천 학교 이야기만. "
            "톤은 선생님이 학생·학부모에게 설명하듯 자연스럽게. "
            "검증 통과한 PDF만 ~/.miho/media_cache/susi_student_record/validated 로 승격하고 "
            "media_tag를 반환한다."
        ),
        "requires": ["student_name", "content"],
    },
    "academy_practical_reco_all_candidates": {
        "domain": "academy_ops",
        "purpose": (
            "수시 실기전형 추천 PDF에서 사용자가 추천 개수를 지정하지 않고 지역 전체 후보를 원할 때 쓴다. "
            "예: '수도권·강원·충청 가능한 학교 다 PDF로 줘', '지역 설정한 모든 학교 보여줘'. "
            "학생명과 사용자가 말한 region만 넘긴다. 사용자가 특정 전형명 포함/예외(예: 지역균형)나 "
            "성별(남자/여자)을 명시하면 admission_track/student_gender도 함께 넘긴다. 기본 전체 후보에 특정 전형을 "
            "예외 추가해야 하면 extra_filters에 대학·학과·전형명을 넣어 같은 추천 파이프라인으로 병합한다. 학교 행·환산점수·전년도 컷·실기종목은 "
            "susi27_recommend_candidates 단일 파이프라인 결과로 코드가 직접 만든다. "
            "academy_practical_reco_package와 같은 practical_reco_shell.html 브랜드 템플릿을 compact 다중 페이지로 쓰므로 "
            "임시 HTML/PDF를 직접 만들지 말 것."
        ),
        "requires": ["student_name", "region"],
    },
    "susi27_recommend_candidates": {
        "domain": "susi_ops",
        "purpose": (
            "수시 실기/교과 추천의 시작점. 학생 성적 조회, 학교별 환산, 전년도 도달성 필터, "
            "지역 필터, 상향/적정 제안을 한 번에 반환한다. 추천 요청에서 룰/계산 도구를 손으로 "
            "조립하지 말고 이 도구를 먼저 사용한다."
        ),
        "requires": ["student_query", "region"],
        "output": "candidate rows with score, full-practical reachability, region, verdict evidence",
        "reviewer": "academy_result_reviewer",
        "retry": "ask for missing region/student, then rerun susi27_recommend_candidates",
        "delivery": "structured Korean table or source payload for practical recommendation PDF",
        "blocking_rules": [
            "do not mention schools absent from the returned candidate list",
            "do not include schools unreachable even with full practical score",
        ],
    },
    "susi27_score_calculate": {
        "domain": "susi_ops",
        "purpose": (
            "verified 수시 룰로 특정 대학/학과의 학생 교과·출결·실기 환산점수를 계산한다. "
            "전체 추천 후보 생성이 아니라 개별 점수 검증과 재계산에 사용한다. "
            "작년 공식 모집요강 또는 전년도 산식과 올해 산식을 비교하는 개인 산식 비교에서는 "
            "susi26_rule_lookup으로 전년도 구조를 확인한 뒤 같은 학생 성적 입력을 근거로 현재 산식 계산표를 만든다."
        ),
        "requires": ["university_id", "grades"],
        "output": "verified score calculation payload with vs_prev_year reachability",
        "reviewer": "academy_result_reviewer",
        "retry": "fix university_id or student score inputs and rerun susi27_score_calculate",
        "delivery": "Korean score breakdown only after review pass",
        "blocking_rules": ["do not invent score values without this payload"],
    },
    "susi26_rule_lookup": {
        "domain": "susi_ops",
        "purpose": (
            "작년 공식 모집요강, 전년도 입학처 PDF, 작년 산식, 작년 점수와 올해 점수 차이를 묻는 "
            "개인 산식 비교의 첫 근거 조회 도구다. 작년 내신:실기 비중, 실기만점, 정원, "
            "실기 종목, 전년도 구조를 확인하고, 근거가 빈약하면 공식 PDF/web source 확보로 넘어가야 한다. "
            "PDF라는 단어가 있어도 pixel_document_evidence만으로 완료하지 말고 산식 계산 목표를 유지한다."
        ),
        "requires": ["university", "department or admission_track when known"],
        "output": "previous-year admission structure and score-scale evidence",
        "reviewer": "academy_result_reviewer",
        "retry": "if the returned structure is too small or lacks formula evidence, obtain official source evidence before answering",
        "delivery": "previous-year formula evidence paired with current susi27_score_calculate breakdown",
        "blocking_rules": ["do not treat document OCR or PDF discovery as the final calculation"],
    },
    "hakjong_qualitative_profile": {
        "domain": "academy_ops",
        "purpose": (
            "학종(학생부종합) 정성 프로필 조회 — 학종 관련 모든 대화의 필수 첫 단계. "
            "대학이 서류에서 중점적으로 보는 것(검토축·읽는 방식), 생기부에 박혀야 할 키워드, "
            "과목별 노트, 면접/서류 방어 질문, 최근 입결 참고값을 반환한다. "
            "학종 리포트든 채팅 상담이든 학종 질문이면 무조건 이 프로필을 먼저 보고 그 기준으로 말한다 — "
            "프로필 없는 전형은 평가 중점을 추측하지 않는다고 밝힌다."
        ),
        "requires": ["university"],
    },
    "hakjong_storm_prewrite": {
        "domain": "academy_ops",
        "purpose": (
            "학종 PDF 작성 전 안전한 사전조사/질문 설계 도구. "
            "life_record_lookup/search/summary, hakjong_qualitative_profile, susi27_rule_lookup으로 근거를 확인한 뒤 "
            "관점별 질문·근거 슬롯·아웃라인·과잉해석 리스크를 만든다. "
            "이 출력만으로 합불/추천/최종판단/PDF를 만들지 말고, academy_hakjong_report_package에 넣을 근거 구조를 정리하는 용도로만 쓴다."
        ),
        "requires": ["student_stage", "qualitative_profile", "student_record_facts"],
    },
    "academy_hakjong_report_package": {
        "domain": "academy_ops",
        "purpose": (
            "내용 JSON만 주면 껍데기(로고/푸터/브랜딩)는 고정 템플릿이 보장한다. "
            "호출 전 hakjong_qualitative_profile로 해당 전형의 평가 기준(검토축·생기부 키워드)을 "
            "반드시 먼저 확인하고, 전형 구조(susi27_rule_lookup)와 생기부(life_record_lookup/search/summary)를 "
            "근거로 섹션 내용을 작성하라. hakjong_storm_prewrite는 선택이 아니라 필수다. "
            "관점별 질문·근거 슬롯·과잉해석 리스크를 먼저 정리한 뒤, 근거 있는 내용만 이 PDF 패키지에 넣는다. "
            "글쓰기 톤: 학원 선생님이 학생·학부모에게 상담하며 설명하는 따뜻하고 자연스러운 말투 — "
            "딱딱한 보고서체('~한다/~이다' 나열) 금지. "
            "내부 판단 과정·배제 설명('OO 분야는 제외하고' 류)은 쓰지 말고, "
            "사용자가 지정한 학교·학과 내용만 직접적으로 쓴다. "
            "terminal/write_file/execute_code로 HTML/PDF를 직접 만들지 마라 — "
            "정식본은 이 도구가 생성한 manifest_version=2, generator=academy_hakjong_report_package, "
            "schema/pdf checks 포함 파일뿐이다. "
            "도구가 반려(ok=false)하면 사용자에게 실패 보고로 끝내지 말고 errors를 수정 체크리스트로 삼아 "
            "같은 턴에서 content를 보강해 재호출한다. 수정 가능한 반려에서 최종 답변 금지 — "
            "통과본 media_tag가 나올 때까지 반복한다. "
            "검증 통과한 PDF만 ~/.miho/media_cache/susi_student_record/validated 로 승격하고 "
            "media_tag를 반환한다."
        ),
        "requires": ["student_name", "student_stage", "evidence_tools", "content"],
    },
    "academy_render_image": {
        "domain": "academy_ops",
        "purpose": (
            "학원 데이터/리포트/표를 Discord 전달용 PNG로 렌더링한다. "
            "전용 이미지 도구가 정확히 맞지 않을 때만 HTML 기반으로 사용한다. "
            "수시 실기전형 추천·내신환산 결과는 여기서 표로 만들지 말고 academy_practical_reco_package(고정 PDF)를 쓴다."
        ),
        "requires": ["safe html body"],
    },
    "academy_report_image": {
        "domain": "academy_ops",
        "purpose": (
            "고정된 표 형식의 학원 리포트를 PNG로 렌더링한다. "
            "열과 행이 명확한 표/기록표/명단형 자료에만 사용한다. "
            "수시 실기전형 추천·내신환산 결과는 여기서 만들지 말고 academy_practical_reco_package(고정 PDF)를 쓴다."
        ),
        "requires": ["columns", "rows"],
    },
    "html_pdf_quality_gate": {
        "domain": "artifact",
        "purpose": (
            "새로 제작하는 한국어 상담자료·운동 프로그램·교육 가이드·업무 제안 PDF의 기본 경로다. "
            "사용자가 처음부터 PDF를 달라고 하거나, 직전 답변/스레드 내용을 PDF로 정리해달라고 하면 "
            "본문 에이전트는 먼저 자체 포함 HTML을 만들고 이 HTML-first 품질 게이트를 호출한다. "
            "이 도구는 PDF 렌더링, 메타데이터 제거, 페이지 PNG/contact sheet 생성, 기본 검수를 수행한다. "
            "PyMuPDF/ReportLab/fitz 좌표 그리기 스크립트로 새 PDF를 직접 만들지 말고, "
            "통과한 pdf_path만 media_delivery_contract로 첨부한다. "
            "이미 존재하는 고정 입시 패키지는 이 도구가 아니라 academy_hakjong_report_package 또는 "
            "academy_practical_reco_package/all_candidates를 쓴다."
        ),
        "requires": ["self-contained html_path", "pdf_path"],
    },
    "html_pdf_autocorrect": {
        "domain": "artifact",
        "purpose": (
            "html_pdf_quality_gate의 contact sheet/vision reviewer가 footer 밀림, 줄 정렬, "
            "텍스트 겹침, 페이지 잘림, 디자인 품질 문제를 지적했을 때 HTML 원본에 "
            "print-safe CSS와 footer/page-break guard를 주입한다. "
            "의미 내용을 새로 쓰는 도구가 아니며, 보정 후 반드시 html_pdf_quality_gate와 "
            "vision_analyze를 다시 통과시킨 뒤 media_delivery_contract로 첨부한다."
        ),
        "requires": ["html_path", "visual_review"],
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
            "실기/수시 추천은 susi27_recommend_candidates 한 번 호출로 시작한다 — "
            "성적 조회·학교별 환산·만점 도달성 필터·정렬을 코드가 전부 처리해 후보 목록을 준다. "
            "룰/계산 도구를 손으로 조립하지 마라(느리고 틀린다). "
            "정시(수능 성적) 상담만 jungsi_student_university_score를 쓴다. "
            "후보 목록에서 최종 학교를 고르고 상향/적정 분류와 근거를 서술한다. "
            "분류 절대 규칙: 상향 = 현재 환산으로는 전년도 컷에 못 미치지만 "
            "(학생 내신환산 + 실기 만점) ≥ 전년도 최종합격 점수라서 실기로 뒤집을 수 있는 학교만. "
            "실기를 만점 받아도 전년도 결과에 못 닿는 학교는 상향이 아니라 수학적으로 불가능 — "
            "어떤 분류로도 추천 목록에 절대 넣지 말 것. "
            "점수 없이 추천을 확정하지 말 것. 모든 후보에 내신환산·실기만점·실기만점 합산·전년도 최초/최종 수치를 병기할 것. "
            "susi27_score_calculate가 돌려주는 vs_prev_year의 reachable_at_full_practical이 false인 학교는 "
            "warning 그대로 — 어떤 분류로도 추천 금지. "
            "추천 확정 전 전년도 크로스체크: 각 후보의 올해 룰(내신 만점·실기 만점·실기 종목·비중)과 "
            "전년도 결과(admission_result_26의 record_score/practical_score 구조)를 대조하라. "
            "작년 합격자 내신환산이 올해 내신 만점보다 크거나, 실기 종목/비중이 달라 보이면 "
            "전형 구조가 바뀐 것 — 단순 점수 비교가 무효일 수 있으니 해당 학교에 '전형 변경' 주의를 달되, "
            "작년에는 어떻게 반영됐는지(작년 비중/만점/종목 수치)와 올해 바뀐 내용을 함께 적어 "
            "비교를 보정하거나 사용자에게 확인을 구하라. "
            "주의: 실기전형은 내신 환산점수+실기 종목+전년도 결과로 판단한다 — "
            "생기부 세특/서사/스토리/학종 언어는 실기전형 추천에 넣지 말 것 (그건 학종 리포트 전용)."
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
    "terminal": {
        "domain": "terminal",
        "purpose": (
            "현재 로컬/서버 운영 상태를 직접 확인하는 실행 진단 도구다. "
            "SSH 접속, IP 변경, 프로세스, 포트, 네트워크, 크론 실행 여부, 로그, 파일 존재, "
            "서비스 상태처럼 지금 머신이나 연결된 서버에서 확인해야 하는 요청은 과거 기억보다 이 도구를 우선한다. "
            "파괴적 명령이나 배포/수정은 별도 승인·검증이 필요하며, 상담/PDF/입시 산출물 생성에는 쓰지 않는다."
        ),
        "requires": ["safe diagnostic command"],
        "output": "current runtime evidence from the local shell or reachable host",
        "reviewer": "dev_result_reviewer",
        "retry": "run narrower read-only diagnostics when the first command is inconclusive",
        "delivery": "Korean answer with the checked command result and remaining uncertainty",
        "blocking_rules": ["do not use for artifact/PDF creation or destructive operations"],
    },
    "session_search": {
        "domain": "session_search",
        "purpose": (
            "과거 대화와 이전 세션 기록을 찾는 회상 도구다. "
            "사용자가 예전에 말한 값, 이전 결정, 과거 산출물 위치를 물을 때 사용한다. "
            "현재 IP, 현재 SSH 접속 가능 여부, 지금 크론이 도는지, 현재 프로세스/로그처럼 "
            "실시간 상태를 직접 확인해야 하는 요청은 이 도구만으로 확정하지 말고 terminal 진단을 우선한다."
        ),
        "requires": ["past-session query"],
        "output": "past transcript snippets from the local session database",
        "reviewer": "governance_result_reviewer",
        "retry": "narrow the query or search around a known message when recall is weak",
        "delivery": "Korean summary that clearly labels recalled past context",
        "blocking_rules": ["do not present recalled stale state as current runtime evidence"],
    },
    "apply_patch": {
        "domain": "dev_tools",
        "purpose": "승인된 코드 변경 범위에서 repository patch를 적용한다. 일반 상담/학원 산출물에는 사용하지 않는다.",
        "requires": ["unified patch", "repo scope"],
        "output": "patch application result",
        "reviewer": "dev_result_reviewer",
        "retry": "fix patch conflicts and rerun focused tests",
        "delivery": "code diff summary after tests",
        "blocking_rules": ["do not use for academy artifact generation"],
    },
    "web_search": {
        "domain": "research",
        "purpose": "최신/외부 사실 확인이 필요한 리서치에서 source attribution을 확보한다.",
        "requires": ["current-fact query"],
        "output": "cited current-fact evidence",
        "reviewer": "research_result_reviewer",
        "retry": "search more authoritative sources when evidence is weak",
        "delivery": "Korean answer with source links and uncertainty",
        "blocking_rules": ["do not invent current facts without sources"],
    },
    "memory": {
        "domain": "memory",
        "purpose": "사용자가 확인한 재사용 가능 사실과 반복 실패 교정을 저장한다. 임시 원문이나 민감정보 저장 금지.",
        "requires": ["confirmed durable memory fact"],
        "output": "memory write confirmation",
        "reviewer": "memory_result_reviewer",
        "retry": "redact or narrow memory content before retry",
        "delivery": "short Korean confirmation only when user-facing",
        "blocking_rules": ["do not store raw sensitive data or one-off temporary state"],
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
    return {
        name: normalize_tool_contract(name, contract, source=_contract_source(name, contract))
        for name, contract in sorted(contracts.items())
    }


def _registered_tool_contracts() -> dict[str, dict[str, Any]]:
    _ensure_tool_discovery()
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
            "schema_required": _schema_required(schema),
        }
    return contracts


def _ensure_tool_discovery() -> None:
    global _DISCOVERY_ATTEMPTED
    if _DISCOVERY_ATTEMPTED:
        return
    _DISCOVERY_ATTEMPTED = True
    try:
        from tools.registry import discover_builtin_tools

        discover_builtin_tools()
    except Exception as exc:
        logger.debug("decision twin builtin tool discovery unavailable: %s", exc)
    try:
        from miho_cli.plugins import discover_plugins

        discover_plugins()
    except Exception as exc:
        logger.debug("decision twin plugin discovery unavailable: %s", exc)


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


def _schema_required(schema: dict[str, Any]) -> list[str]:
    required = schema.get("required")
    if not isinstance(required, list):
        params = schema.get("parameters")
        if isinstance(params, dict):
            required = params.get("required")
    if not isinstance(required, list):
        return []
    return [str(name) for name in required if str(name or "").strip()]


def _contract_source(name: str, contract: dict[str, Any]) -> str:
    if name in _CORE_CONTRACTS:
        return "decision_twin_core"
    if "aliases" in contract:
        return "academy_tool_registry"
    return "tool_registry"


def _compact(value: str, limit: int = 360) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
