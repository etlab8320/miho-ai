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
