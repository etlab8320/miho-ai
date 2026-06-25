"""Live research support for hakjong qualitative reports."""
from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hakjong_faculty_research import build_faculty_research, paper_titles_from_bundle, recover_existing_faculty_research, sanitize_faculty_profiles, sanitize_faculty_paper_sources, bundle_sources_match_university
from .hakjong_live_refresh import choose_best_bundle, copy_section, failed_results, section_fresh, section_ttls
_LIVE_KEYWORDS = (
    "스포츠", "체육", "운동", "신체활동", "건강", "건강증진", "체력", "측정",
    "평가", "정밀 분석", "데이터", "운동생리", "운동역학", "스포츠의학", "재활",
    "운동처방", "손상", "부상", "노인", "청소년", "보디빌딩", "사회적 책임", "공감",
    "참여 격차", "도핑", "웨어러블", "디지털", "트레이닝", "기능평가",
)
_LIVE_FLOW_LABEL = "최신 학과 흐름"
_SCHOLAR_MAILTO = os.environ.get("MIHO_HAKJONG_RESEARCH_MAILTO", "etlab@example.com")
_DEFAULT_TTL_HOURS = 24.0
def bundle_dir_for_db(path: Path) -> Path:
    return path.parent / "school_specific_source_bundles"

def safe_slug_part(value: Any) -> str:
    text = str(value or "").strip()
    return "".join(ch if (ch.isalnum() or ch in "_-가-힣") else "_" for ch in text).strip("_")

def latest_live_research_bundle(
    path: Path,
    *,
    university: str,
    department: str,
    admission_track: str,
) -> dict[str, Any] | None:
    bundle_dir = bundle_dir_for_db(path)
    if not bundle_dir.exists():
        return None
    slug = "_".join(
        part
        for part in (safe_slug_part(university), safe_slug_part(department), safe_slug_part(admission_track))
        if part
    )
    patterns = [f"{slug}_live_research*.json", f"{slug}*live*.json"] if slug else ["*live_research*.json"]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(bundle_dir.glob(pattern))
    if not candidates:
        labels = [p for p in (safe_slug_part(university), safe_slug_part(department), safe_slug_part(admission_track)) if p]
        for candidate in bundle_dir.glob("*.json"):
            if all(label in candidate.stem for label in labels):
                candidates.append(candidate)
    if not candidates:
        return None
    chosen = choose_best_bundle(candidates)
    if chosen is None:
        return None
    newest, data = chosen
    if not bundle_sources_match_university(data, university):
        data["faculty_profiles"], data["faculty_paper_sources"] = [], []
    data["faculty_profiles"] = sanitize_faculty_profiles(data.get("faculty_profiles") or [])
    data["faculty_paper_sources"] = sanitize_faculty_paper_sources(data.get("faculty_paper_sources") or [], str(data.get("university") or ""))
    data.setdefault("bundle_path", str(newest))
    return data

def bundle_is_fresh(bundle: dict[str, Any] | None) -> bool:
    if not isinstance(bundle, dict):
        return False
    try:
        ttl_hours = float(os.environ.get("MIHO_HAKJONG_LIVE_RESEARCH_TTL_HOURS", str(_DEFAULT_TTL_HOURS)))
    except ValueError:
        ttl_hours = _DEFAULT_TTL_HOURS
    if ttl_hours <= 0:
        return False
    raw = str(bundle.get("searched_at") or "").strip()
    if not raw:
        return False
    try:
        searched = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    if searched.tzinfo is None:
        searched = searched.replace(tzinfo=timezone.utc)
    age_hours = (datetime.now(timezone.utc) - searched.astimezone(timezone.utc)).total_seconds() / 3600
    return age_hours <= ttl_hours


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _live_enabled() -> bool:
    return os.environ.get("MIHO_HAKJONG_LIVE_RESEARCH", "1").strip().lower() not in {"0", "false", "off", "no"}


def _strip_html(raw: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", raw, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _open_url(url: str, *, accept: str = "application/json", timeout: int = 6) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Miho Hakjong LiveResearch", "Accept": accept},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(500_000).decode("utf-8", errors="ignore")


def search_web_snippets(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    encoded = urllib.parse.quote(query)
    url = f"https://search.naver.com/search.naver?query={encoded}"
    try:
        raw = _open_url(url, accept="text/html", timeout=6)
    except Exception as exc:
        return [{"title": "검색 실패", "snippet": str(exc), "url": url, "source": "naver"}]
    text = _strip_html(raw)
    snippets: list[dict[str, str]] = []
    seen: set[str] = set()
    first = query.split()[0] if query.split() else query
    start = text.find(first) if first else -1
    while start >= 0:
        snippet = text[max(0, start - 90): start + len(first) + 160].strip()
        if len(snippet) < 30 or snippet in seen:
            start = text.find(first, start + max(1, len(first)))
            continue
        seen.add(snippet)
        snippets.append({"title": snippet[:80], "snippet": snippet[:260], "url": url, "source": "naver"})
        if len(snippets) >= limit:
            break
        start = text.find(first, start + max(1, len(first)))
    if not snippets:
        snippets.append({"title": query, "snippet": text[:260], "url": url, "source": "naver"})
    return snippets[:limit]


def search_openalex(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    params = urllib.parse.urlencode({
        "search": query,
        "per-page": str(limit),
        "mailto": _SCHOLAR_MAILTO,
        "select": "title,publication_year,doi,primary_topic,authorships",
    })
    url = f"https://api.openalex.org/works?{params}"
    try:
        data = json.loads(_open_url(url, timeout=7))
    except Exception as exc:
        return [{"title": "OpenAlex 검색 실패", "snippet": str(exc), "url": url, "source": "openalex"}]
    out: list[dict[str, str]] = []
    for item in data.get("results") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        topic = item.get("primary_topic") if isinstance(item.get("primary_topic"), dict) else {}
        topic_name = str(topic.get("display_name") or "").strip()
        year = str(item.get("publication_year") or "").strip()
        authors = []
        for auth in item.get("authorships") or []:
            if isinstance(auth, dict) and isinstance(auth.get("author"), dict):
                authors.append(str(auth["author"].get("display_name") or "").strip())
        snippet = " / ".join(x for x in [year, topic_name, ", ".join(a for a in authors[:3] if a)] if x)
        out.append({"title": title[:120] or query, "snippet": snippet[:260], "url": str(item.get("doi") or url), "source": "openalex"})
    return out[:limit]


def search_crossref(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    params = urllib.parse.urlencode({
        "query.bibliographic": query,
        "rows": str(limit),
        "select": "title,URL,DOI,published-print,published-online,container-title,subject,author",
        "mailto": _SCHOLAR_MAILTO,
    })
    url = f"https://api.crossref.org/works?{params}"
    try:
        data = json.loads(_open_url(url, timeout=7))
    except Exception as exc:
        return [{"title": "Crossref 검색 실패", "snippet": str(exc), "url": url, "source": "crossref"}]
    out: list[dict[str, str]] = []
    for item in ((data.get("message") or {}).get("items") or []):
        if not isinstance(item, dict):
            continue
        title = " ".join(str(v) for v in (item.get("title") or []) if v).strip()
        journal = " ".join(str(v) for v in (item.get("container-title") or []) if v).strip()
        subjects = ", ".join(str(v) for v in (item.get("subject") or [])[:4])
        authors = ", ".join(
            " ".join(part for part in [str(a.get("given") or ""), str(a.get("family") or "")] if part).strip()
            for a in (item.get("author") or [])[:4]
            if isinstance(a, dict)
        )
        out.append({"title": title[:120] or query, "snippet": " / ".join(x for x in [journal, subjects, authors] if x)[:260], "url": str(item.get("URL") or url), "source": "crossref"})
    return out[:limit]


def search_kci(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    key = os.environ.get("MIHO_KCI_API_KEY") or os.environ.get("KCI_OPEN_API_KEY")
    if not key:
        return []
    params = urllib.parse.urlencode({"apiCode": "articleSearch", "key": key, "title": query, "displayCount": str(limit)})
    url = f"https://open.kci.go.kr/po/openapi/openApiSearch.kci?{params}"
    try:
        root = ET.fromstring(_open_url(url, accept="application/xml", timeout=7))
    except Exception as exc:
        return [{"title": "KCI 검색 실패", "snippet": str(exc), "url": url, "source": "kci"}]
    out: list[dict[str, str]] = []
    for node in root.iter():
        children = {child.tag.lower(): (child.text or "").strip() for child in list(node)}
        title = children.get("article-title") or children.get("title") or children.get("articlename")
        if not title:
            continue
        author = children.get("author") or children.get("authors")
        journal = children.get("journal-name") or children.get("journal")
        out.append({"title": title[:120], "snippet": " / ".join(x for x in [author, journal] if x)[:260], "url": url, "source": "kci"})
        if len(out) >= limit:
            break
    return out


def keywords_from_text(text: str, *, department: str = "", limit: int = 10) -> list[str]:
    found: list[str] = []
    hay = f"{department} {text}"
    for kw in _LIVE_KEYWORDS:
        if kw in hay and kw not in found:
            found.append(kw)
    if "체육" in department and "체육" not in found:
        found.append("체육")
    if "스포츠" in department and "스포츠" not in found:
        found.append("스포츠")
    if "스포츠과학" in department and "스포츠과학" not in found:
        found.append("스포츠과학")
    if "건강" in department and "건강증진" not in found:
        found.append("건강증진")
    if "재활" in department and "재활" not in found:
        found.append("재활")
    return found[:limit]


def write_live_research_bundle(
    path: Path,
    *,
    university: str,
    department: str,
    admission_track: str,
    existing: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not _live_enabled():
        return None
    bundle_dir = bundle_dir_for_db(path)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    searched_at = _now_utc_iso()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = "_".join(part for part in (safe_slug_part(university), safe_slug_part(department), safe_slug_part(admission_track)) if part) or "hakjong"
    faculty_query = f"{university} {department} 교수진"
    paper_query = f"{university} {department} 스포츠 체육 논문 연구"
    news_query = f"{university} {department} 뉴스 최신 스포츠 과학"
    ttls = section_ttls()
    status: dict[str, str] = {}
    faculty_research: dict[str, Any] = {}

    if section_fresh(existing, "faculty_live_sources", ttls["faculty"]):
        faculty_rows = copy_section(existing, "faculty_live_sources")
        faculty_snips = faculty_rows[0].get("results", []) if faculty_rows else []
        status["faculty"] = "cache_fresh"
    else:
        faculty_snips = search_web_snippets(faculty_query, limit=4)
        if failed_results(faculty_snips) and copy_section(existing, "faculty_live_sources"):
            faculty_rows = copy_section(existing, "faculty_live_sources")
            faculty_snips = faculty_rows[0].get("results", [])
            status["faculty"] = "cache_fallback_after_live_failure"
        else:
            faculty_rows = []
            status["faculty"] = "live_refreshed"

    paper_cache_ready = (
        section_fresh(existing, "paper_title_live_probe", ttls["paper"])
        and bool(copy_section(existing, "scholarly_sources"))
        and bool((existing or {}).get("faculty_paper_sources"))
    )
    if paper_cache_ready:
        scholarly = copy_section(existing, "scholarly_sources")
        faculty_research = {
            "faculty_profiles": (existing or {}).get("faculty_profiles") or [],
            "faculty_source_pages": (existing or {}).get("faculty_source_pages") or [],
            "faculty_paper_sources": (existing or {}).get("faculty_paper_sources") or [],
            "faculty_query_log": (existing or {}).get("faculty_query_log") or [],
        }
        status["paper"] = "cache_fresh"
    else:
        def scholarly_search(query: str) -> list[dict[str, str]]:
            return search_kci(query, limit=3) + search_openalex(query, limit=3) + search_crossref(query, limit=3)
        faculty_research = build_faculty_research(
            university,
            department,
            scholarly_search=scholarly_search,
            max_faculty=5,
        )
        faculty_research = recover_existing_faculty_research(faculty_research, existing)
        scholarly = (
            faculty_research.get("faculty_paper_sources") or []
        ) + scholarly_search(paper_query)
        if failed_results(scholarly) and copy_section(existing, "scholarly_sources"):
            scholarly = copy_section(existing, "scholarly_sources")
            status["paper"] = "cache_fallback_after_live_failure"
        else:
            status["paper"] = "live_refreshed"

    if section_fresh(existing, "field_news_live_probe", ttls["news"]):
        news_snips = copy_section(existing, "field_news_live_probe")
        status["news"] = "cache_fresh"
    else:
        news_snips = search_web_snippets(news_query, limit=4)
        if failed_results(news_snips) and copy_section(existing, "field_news_live_probe"):
            news_snips = copy_section(existing, "field_news_live_probe")
            status["news"] = "cache_fallback_after_live_failure"
        else:
            status["news"] = "live_refreshed"

    all_text = " ".join(
        s.get("snippet", "") + " " + s.get("title", "")
        for s in faculty_snips + scholarly + news_snips + (faculty_research.get("faculty_paper_sources") or [])
    )
    keywords = keywords_from_text(all_text, department=department, limit=10)
    confidence = "high" if len(keywords) >= 4 and any(s.get("source") in {"kci", "openalex", "crossref"} for s in scholarly) else ("medium" if len(keywords) >= 2 else "low")
    faculty_section = faculty_rows or [{"source_type": "live_search", "query": faculty_query, "results": faculty_snips, "keywords": keywords, "searched_at": searched_at}]
    for item in faculty_section:
        item.setdefault("searched_at", searched_at)
    for item in scholarly + news_snips:
        item.setdefault("searched_at", searched_at)
    bundle: dict[str, Any] = {
        "probe_type": "live_research_auto",
        "searched_at": searched_at,
        "university": university,
        "department": department,
        "admission_track": admission_track,
        "source_policy": "official profile first, scholarly APIs second, web/news search last",
        "section_ttl_hours": ttls,
        "refresh_status": status,
        "faculty_live_sources": faculty_section,
        "faculty_profiles": faculty_research.get("faculty_profiles") or [],
        "faculty_source_pages": faculty_research.get("faculty_source_pages") or [],
        "faculty_paper_sources": faculty_research.get("faculty_paper_sources") or [],
        "scholarly_sources": scholarly,
        "paper_title_live_probe": [{"query": paper_query, "search_source": "kci_openalex_crossref", "hits_or_titles": [s.get("title", "") for s in scholarly if s.get("title")], "usable_keywords": keywords, "searched_at": searched_at}],
        "field_news_live_probe": [{"query": news_query, "source": s.get("source", "naver"), "title": s.get("title", news_query), "url": s.get("url", ""), "snippet": s.get("snippet", ""), "keywords": keywords, "searched_at": s.get("searched_at", searched_at)} for s in news_snips],
        "query_log": [faculty_query, paper_query, news_query, *(faculty_research.get("faculty_query_log") or [])],
        "confidence": confidence,
        "limits": [
            "자동 live search 결과는 교수 연구·최신뉴스 보조 근거이며 공식 전형 판단보다 우선하지 않는다.",
            "OpenAlex/Crossref는 영문·국제 메타데이터가 강하고, KCI는 API key가 있을 때 국내 학술지 보강용으로 사용한다.",
            "논문 원문 전문 검증이 아니라 제목·스니펫·키워드 중심 캐시다.",
        ],
    }
    out = bundle_dir / f"{slug}_live_research_auto_{stamp}.json"
    try:
        out.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return None
    bundle["bundle_path"] = str(out)
    return bundle


def live_research_bundle(
    path: Path,
    *,
    university: str,
    department: str,
    admission_track: str,
) -> dict[str, Any] | None:
    if not _live_enabled():
        return None
    existing = latest_live_research_bundle(
        path,
        university=university,
        department=department,
        admission_track=admission_track,
    )
    ttls = section_ttls()
    if (
        section_fresh(existing, "faculty_live_sources", ttls["faculty"])
        and section_fresh(existing, "paper_title_live_probe", ttls["paper"])
        and section_fresh(existing, "field_news_live_probe", ttls["news"])
        and bool((existing or {}).get("faculty_paper_sources"))
    ):
        return existing
    generated = write_live_research_bundle(
        path,
        university=university,
        department=department,
        admission_track=admission_track,
        existing=existing,
    )
    return generated or existing


def live_research_keywords(bundle: dict[str, Any] | None, limit: int = 8) -> list[str]:
    if not isinstance(bundle, dict):
        return []
    blocked = {"AI", "인공지능", "Year", "Month", "Day", "검색옵션", "초기화", "가이드", "Sejong", "할 수 있고", "스포츠", "체육", "운동", "건강", "재활", "디지털"}
    keywords: list[str] = []
    for section_name in ("paper_title_live_probe", "field_news_live_probe"):
        section = bundle.get(section_name)
        if isinstance(section, list):
            for item in section:
                if isinstance(item, dict):
                    for key in ("usable_keywords", "keywords"):
                        values = item.get(key)
                        if isinstance(values, list):
                            keywords.extend(str(v).strip() for v in values if str(v).strip())
    keywords.extend(part.strip() for profile in bundle.get("faculty_profiles") or [] if isinstance(profile, dict) for part in str(profile.get("major") or "").replace(",", "·").split("·"))
    seen: set[str] = set()
    unique: list[str] = []
    for kw in keywords:
        if kw in seen or len(kw) > 18 or kw in blocked:
            continue
        seen.add(kw)
        unique.append(kw)
        if len(unique) >= limit:
            break
    return unique

def apply_live_research_enrichment(content: dict[str, Any], profile: dict[str, Any] | None) -> bool:
    if not isinstance(profile, dict):
        return False
    bundle = profile.get("live_research")
    if not isinstance(bundle, dict):
        return False
    keywords = live_research_keywords(bundle)
    paper_titles = paper_titles_from_bundle(bundle, limit=1)
    if len(keywords) < 2 and paper_titles:
        keywords.append("교수논문")
    if len(keywords) < 2:
        return False
    content_text = _content_text(content)
    if sum(1 for kw in keywords if kw in content_text) >= 2 and _has_live_flow_row(content) and not paper_titles:
        return False
    keyword_text = "·".join(keywords[:6])
    evidence_text = " / ".join(paper_titles) if paper_titles else f"교수진·논문·뉴스 키워드: {keyword_text}"
    live_note = f"최신 학과 흐름 반영: {keyword_text}"
    track = content.setdefault("track_section", {})
    if isinstance(track, dict):
        rows = track.setdefault("rows", [])
        if isinstance(rows, list):
            live_rows = [r for r in rows if isinstance(r, dict) and r.get("label") == _LIVE_FLOW_LABEL]
            row = {"label": _LIVE_FLOW_LABEL, "official": f"교수 연구 제목: {evidence_text}", "judgment": f"세특은 {keyword_text} 중심으로 압축하면 학과 적합성이 선명해진다."}
            live_rows[0].update(row) if live_rows else rows.append(row)
        strong = track.get("strong_points")
        if isinstance(strong, dict):
            bullets = strong.setdefault("bullets", [])
            if isinstance(bullets, list) and not any(_LIVE_FLOW_LABEL in str(b) for b in bullets):
                bullets.append(f"{_LIVE_FLOW_LABEL}과 연결 가능한 키워드: {keyword_text}")
    strategy = content.setdefault("strategy_section", {})
    if isinstance(strategy, dict):
        actions = strategy.get("actions")
        if isinstance(actions, list) and actions and isinstance(actions[-1], dict) and _LIVE_FLOW_LABEL not in str(actions[-1].get("body") or ""):
            actions[-1]["body"] = (str(actions[-1].get("body") or "").rstrip(". ") + f". {live_note}을 {'서류 해석 문장' if '완성 생기부' in str(strategy.get('heading') or '') else '학생부 보완 문장'}에 반영한다.").strip()
        interview_rows = strategy.setdefault("interview_rows", [])
        if isinstance(interview_rows, list) and interview_rows and not any(isinstance(r, dict) and _LIVE_FLOW_LABEL in str(r.get("question") or "") for r in interview_rows):
            point = (
                f"{keyword_text} 중 학생 기록과 닿는 키워드를 고르고, 기존 세특의 측정·분석·보완 과정과 "
                "한계까지 말해 면접관 꼬리질문에 방어한다."
            )
            interview_rows.append({"question": f"{_LIVE_FLOW_LABEL}과 본인 활동은 어떻게 연결되는가?", "point": point})
        final = strategy.get("final_judgment")
        if isinstance(final, dict) and _LIVE_FLOW_LABEL not in str(final.get("body") or ""):
            final["body"] = str(final.get("body") or "").rstrip(". ") + f". {live_note}을 기준으로 {'면접 답변' if '완성 생기부' in str(strategy.get('heading') or '') and isinstance(strategy.get('interview_rows'), list) and strategy.get('interview_rows') else '기록 해석 문장' if '완성 생기부' in str(strategy.get('heading') or '') else '세특·면접 답변' if isinstance(strategy.get('interview_rows'), list) and strategy.get('interview_rows') else '세특 보완 문장'}을 정리해야 한다."
        footnote = str(strategy.get("footnote") or "").strip()
        if _LIVE_FLOW_LABEL not in footnote:
            strategy["footnote"] = (footnote + " " + live_note).strip()
    return True


def _has_live_flow_row(content: dict[str, Any]) -> bool:
    track = content.get("track_section")
    if not isinstance(track, dict):
        return False
    rows = track.get("rows")
    return isinstance(rows, list) and any(isinstance(r, dict) and r.get("label") == _LIVE_FLOW_LABEL for r in rows)


def _content_text(content: dict[str, Any]) -> str:
    parts: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, str):
            parts.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)

    walk(content)
    return " ".join(parts)
