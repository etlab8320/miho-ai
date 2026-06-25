"""Physical PDF validation contract for hakjong report delivery.

After T2+T3 refactor: HTML/CSS pattern checks are gone (the fixed shell
template guarantees structure). What remains is the PDF physical validator
used by hakjong_report_tool, the quality constants used by
hakjong_report_schema, and the evidence-tool sets shared by both.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .hakjong_stage_contract import has_early_context_evidence, validate_stage_contract  # noqa: F401


BRAND_TEXT = "맥스체대입시 일산교육원"

# 학종 리포트 전용 금지어 — 학종은 생기부(교과·세특·활동) 서사만 다룬다.
# 실기 측정 기록·타전형 비교("실기우수자와 다르게")가 끼는 순간 학종 문서가 아니다
# (2026-06-12 실사고: Peak 실기 기록을 학종 핵심판단에 끌어옴). 실기 추천 PDF는
# 별도 도구이므로 이 목록은 학종 스키마만 쓴다.
BANNED_HAKJONG_ONLY_TEXT = (
    "실기",
)

BANNED_PDF_TEXT = (
    # 내부 검증 라벨/검토 과정 언어 — 학생·학부모가 볼 문서에 절대 노출 금지
    # (사장님 2026-06-12: "verified 산식, 제외/보류 판단 이런건 절대 나오면 안되고").
    "verified",
    "confidence",
    "산식",
    "보류",
    "제외",
    "MIHO AI",
    "MAX SPORTS ADMISSION",
    "source_thread",
    "profile_ready",
    "needs_review",
    "file://",
    "자료 기준",
    "학생 생활기록부 데이터",
    "생활기록부 데이터",
    "생활기록부 데이터 기준",
    "공식 전형자료",
    "대학 공식 전형자료",
    "산출 데이터 기준",
    "기준으로 구성",
    "기준으로 작성",
    "기준으로 분석",
    "제작 기준",
    "본 리포트는",
    "프리미엄",
    "인공지능",
    "AI",
    # AI 티 나는 공허한 메타 클리셰 — 구체 활동/결과 대신 추상 표현 (사장님 2026-06-13: "진짜 AI가 쓴 것 같다")
    "언어로 정렬",
    "언어로 재구성",
    "언어로 풀어",
    "전공 언어로",
    "스포츠과학 언어로",
    "관점에서 재해석",
    # 컨설턴트→학생 메타 지시·생기부 조작 톤이 본문에 새는 것 (사장님 2026-06-14: "쓰게 만드는게 뭔데, 학생입장에서 어색")
    "쓰게 만든다",
    "쓰게 한다",
    "라고 쓴다",
    "남긴다고 쓴다",
    "쓰도록 한다",
    # "말할/설명할 수 있게 만든다" 류 — 학생을 그렇게 만든다는 조작 톤 (사장님 2026-06-14 박지호 고1)
    "수 있게 만든다",
)

MIN_REPORT_CARD_COUNT = 6
MIN_VISIBLE_TEXT_CHARS = 1_600
MIN_SUBSTANTIVE_SEGMENTS = 5
MIN_SUBSTANTIVE_SEGMENT_CHARS = 55
MAX_VISIBLE_TEXT_SEGMENT_CHARS = 230

LIFE_RECORD_EVIDENCE_TOOLS = {
    "life_record_lookup",
    "life_record_summary",
    "life_record_search",
    "life_record_verify",
}

HAKJONG_EVIDENCE_TOOLS = {
    "hakjong_profile",
    "qualitative_profile",
    "qualitative_profiles_md",
    "susi_engine",
    "admission_profile",
}


def _pdf_info(pdf_path: Path) -> dict[str, Any]:
    if shutil.which("pdfinfo") is None:
        return {"error": "pdfinfo is not available"}
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": f"pdfinfo failed: {exc}"}
    if result.returncode != 0:
        return {"error": f"pdfinfo failed: {result.stderr.strip() or result.stdout.strip()}"}
    return _parse_pdfinfo(result.stdout)


def _parse_pdfinfo(output: str) -> dict[str, Any]:
    pages = None
    width = None
    height = None
    for line in output.splitlines():
        if line.startswith("Pages:"):
            pages = _int_or_none(line.split(":", 1)[1].strip())
        elif line.startswith("Page size:"):
            match = re.compile(r"([\d.]+)\s+x\s+([\d.]+)\s+pts").search(line)
            if match:
                width = float(match.group(1))
                height = float(match.group(2))
    return {"pages": pages, "width": width, "height": height}


def _pdf_text(pdf_path: Path) -> dict[str, Any]:
    if shutil.which("pdftotext") is None:
        return {"error": "pdftotext is not available"}
    try:
        result = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": f"pdftotext failed: {exc}"}
    if result.returncode != 0:
        return {"error": f"pdftotext failed: {result.stderr.strip() or result.stdout.strip()}"}
    return {"text": result.stdout}


def _matches_hakjong_evidence(tool: str) -> bool:
    return tool in HAKJONG_EVIDENCE_TOOLS or tool.startswith("hakjong_") or "qualitative" in tool


def _int_or_none(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def truncation_errors(content: Any, pdf_text: str, errors: list) -> None:
    """content의 모든 문장이 PDF에 실제로 인쇄됐는지 대조 — 페이지 고정 높이
    (height:297mm + overflow:hidden)를 넘친 내용은 조용히 잘리므로(2026-06-12
    유가은 리포트 마지막 표 잘림) 기계로 감지해 분량 축소를 요구한다.
    공백 차이는 PDF 텍스트 추출 변형이라 제거 후 비교한다."""
    import re

    haystack = "".join(str(pdf_text or "").split())

    def _present(text: str) -> bool:
        needle = "".join(text.split())
        if needle in haystack:
            return True
        # 표 셀이 좁아 여러 줄로 렌더되면 pdftotext가 옆 열 텍스트를 줄 단위로 끼워 넣어
        # 연속 매칭이 깨진다(2026-06-13 false positive: "…수렴," 다음 줄에 다른 열이 삽입).
        # 구두점·공백으로 쪼갠 조각(4자+)이 모두 PDF에 있으면 인쇄된 것으로 본다.
        frags = [f for f in re.split(r"[\s,.;:/&()\[\]··]+", text) if len("".join(f.split())) >= 4]
        return bool(frags) and all("".join(f.split()) in haystack for f in frags)

    def walk(obj: Any) -> None:
        if isinstance(obj, str):
            needle = "".join(obj.split())
            if len(needle) >= 15 and not _present(obj):
                errors.append(
                    f"내용이 페이지를 넘쳐 잘렸다 — \"{obj.strip()[:40]}…\" 가 PDF에 인쇄되지 않았다. "
                    "해당 섹션 문단·행 분량을 줄여 한 페이지 안에 들어가게 하라."
                )
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(content)
