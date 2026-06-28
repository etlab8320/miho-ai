"""PDF layout checks shared by academy report generators."""

from __future__ import annotations

import re
from pathlib import Path


_FOOTER_BOTTOM_BAND_PT = 55.0
_FOOTER_TOP_ORPHAN_PT = 80.0
_TRAILING_PAGE_NUMBER_RE = re.compile(r"\b[0-9]\s*$")
_REPORT_PAGE_RE = re.compile(r"(리포트|report)\s+[0-9]\s*$", re.IGNORECASE)


def footer_layout_errors(pdf_path: Path, *, expected_pages: int | None = None) -> list[str]:
    """Return layout errors for footer anchoring in a rendered PDF."""
    try:
        import fitz  # type: ignore[import-untyped]
    except Exception:
        return []

    errors: list[str] = []
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        return [f"PDF 레이아웃 검증을 위해 파일을 열 수 없다: {exc}"]

    with doc:
        pages = [
            (
                page,
                [
                    block
                    for block in page.get_text("blocks")
                    if len(block) >= 5 and str(block[4] or "").strip()
                ],
            )
            for page in doc
        ]
        if not any(blocks for _page, blocks in pages):
            return []
        if expected_pages is not None and len(doc) > expected_pages:
            errors.append(
                f"PDF가 예상 {expected_pages}페이지보다 많은 {len(doc)}페이지로 렌더됐다. "
                "본문이 footer를 밀어낸 페이지 넘침 가능성이 있다."
            )
        for index, (page, blocks) in enumerate(pages, start=1):
            page_height = float(page.rect.height)
            if not blocks:
                errors.append(f"{index}페이지가 빈 페이지로 렌더됐다.")
                continue

            footer_blocks = [
                block
                for block in blocks
                if float(block[1]) >= page_height - _FOOTER_BOTTOM_BAND_PT
                and _looks_like_footer(str(block[4]))
            ]
            if not footer_blocks:
                errors.append(
                    f"{index}페이지 footer가 하단 고정 위치에서 발견되지 않았다. "
                    "본문 길이 또는 페이지 높이 설정을 줄여 다시 렌더해야 한다."
                )

            top_footer_blocks = [
                block
                for block in blocks
                if float(block[1]) <= _FOOTER_TOP_ORPHAN_PT
                and _looks_like_footer(str(block[4]))
            ]
            if top_footer_blocks and not footer_blocks:
                errors.append(
                    f"{index}페이지에 footer만 다음 페이지 상단으로 밀린 흔적이 있다."
                )
    return errors


def _looks_like_footer(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return False
    if "맥스체대입시" in normalized:
        return True
    if "확인용" in normalized:
        return True
    if _REPORT_PAGE_RE.search(normalized):
        return True
    if _TRAILING_PAGE_NUMBER_RE.search(normalized) and len(normalized) <= 280:
        return True
    return False
