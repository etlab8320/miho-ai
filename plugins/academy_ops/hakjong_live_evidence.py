"""Evidence text helpers for hakjong live research enrichment."""

from __future__ import annotations


def live_evidence_summary(keywords: list[str], paper_titles: list[str]) -> tuple[str, str, str]:
    keyword_text = "·".join(keywords[:6])
    cleaned_titles = _clean_paper_titles(paper_titles)
    if cleaned_titles:
        evidence_text = " / ".join(cleaned_titles)
    else:
        evidence_text = f"교수진·논문·뉴스 키워드: {keyword_text}"
    return keyword_text, evidence_text, f"최신 학과 흐름 반영: {keyword_text}"


def _clean_paper_titles(paper_titles: list[str]) -> list[str]:
    cleaned: list[str] = []
    for title in paper_titles:
        text = " ".join(str(title or "").split()).strip()
        if not text:
            continue
        cleaned.append(text[:56])
    return cleaned
