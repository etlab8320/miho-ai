"""Evidence text helpers for hakjong live research enrichment."""

from __future__ import annotations


def live_evidence_summary(keywords: list[str], paper_titles: list[str]) -> tuple[str, str, str]:
    keyword_text = "·".join(keywords[:6])
    if _can_use_paper_titles(paper_titles):
        evidence_text = " / ".join(paper_titles)
    else:
        evidence_text = f"교수진·논문·뉴스 키워드: {keyword_text}"
    return keyword_text, evidence_text, f"최신 학과 흐름 반영: {keyword_text}"


def _can_use_paper_titles(paper_titles: list[str]) -> bool:
    return bool(
        paper_titles
        and all(len(title) <= 42 and not any(ord(ch) < 128 for ch in title) for title in paper_titles)
    )
