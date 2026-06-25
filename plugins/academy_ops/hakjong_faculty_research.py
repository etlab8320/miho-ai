"""Faculty-first research helpers for hakjong live research."""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any


NOISE_WORDS = (
    "본문", "바로가기", "검색", "메뉴", "이미지", "교수소개", "학과소개",
    "소속", "보직", "전공", "연락처", "연구실", "이메일", "학위취득",
)
NOISE_NAMES = {
    "확인", "지도", "탐색", "직급", "교수", "부설기관", "사범대학", "먼트전공",
    "스포츠", "학과", "대학", "검색어", "담당교과", "홈으로", "특성과", "서식",
    "한글", "사회", "대학생활", "주요경력", "명예", "인사말", "교수진",
    "공지사항", "교과과정", "메뉴닫기", "전공소개", "연구실적", "학력", "연혁",
    "강의체험", "학사일정", "학부소개", "갤러리", "동영상", "졸업", "학사안내",
    "교육과정", "겸임", "주임",
    "부속기관", "전공선택", "검색하기", "직위", "전체메뉴", "유틸메뉴",
    "과학대학", "전공능력", "개요", "구호", "세부전공",
}
NOISE_MAJOR_PARTS = (
    "모집", "우대", "핵심", "교수는", "예술·체육대학", "이름 검색", "화면보기",
    "편입", "기초(필수)", "소개영상", "Undergraduate Admissions", "개인신상관리",
    "소개", "분야", "사무실", "Copyright", "자의 수요",
    "안내", "교과목안내", "CDR", "행사", "공지사항", "가이드북", "역량",
    "세부영역", "인가", "글로벌캠퍼스", "심화과정", "별강의",
    "연락처", "이메일", "홈페이지", "보고서", "다운로드", "커리큘럼",
)
OFFICIAL_HOST_HINTS = {
    "경희대학교": ("khu.ac.kr",),
    "고려대학교": ("korea.ac.kr",),
    "국민대학교": ("kookmin.ac.kr",),
    "상명대학교": ("smu.ac.kr",),
    "서울과학기술대학교": ("seoultech.ac.kr",),
    "서울대학교": ("snu.ac.kr",),
    "서울시립대학교": ("uos.ac.kr",),
    "서울여자대학교": ("swu.ac.kr",),
    "성균관대학교": ("skku.edu",),
    "인천대학교": ("inu.ac.kr",),
    "인하대학교": ("inha.ac.kr",),
    "중앙대학교": ("cau.ac.kr",),
    "한국교원대학교": ("knue.ac.kr",),
    "한국외국어대학교": ("hufs.ac.kr",),
    "한양대학교": ("hanyang.ac.kr",),
}
RESEARCH_TERMS = (
    "스포츠", "체육", "운동", "재활", "건강", "생리", "역학", "보행", "균형", "하지",
    "sport", "exercise", "kinesiology", "biomechanics", "physiology", "rehabilitation",
    "gait", "balance", "physical", "fitness",
    "보디빌딩",
)
FACULTY_PAGE_HINTS = ("전공",)
_ANCHOR_LINK_RE = re.compile(r'<a\b[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', flags=re.I | re.S)
_KOREAN_NAME_WITH_OPTION_RE = re.compile(r"[가-힣]{2,4}(?:\s*\([^)]{1,12}\))?")
_KOREAN_NAME_RE = re.compile(r"[가-힣]{2,4}")
_FIELD_VALUE_TEMPLATE = r"(?:^|[\s|])\**{field}\**\s*[:：|]?\s*([^\n|*]{{2,80}})"
_FACULTY_ROW_RE = re.compile(
    r"교수\s*\|\s*([가-힣]{2,4})\s*\|(?:[^|]{0,40}\|\s*){0,8}(?:주전공|전공|담당교과)\s*\|\s*([^|]{2,80})"
)
_PROFESSOR_MAJOR_LINE_RE = re.compile(r"^교수\s+([^|]{2,60})$")
_NAME_LABEL_RE = re.compile(r"성명\s*[:：]\s*([가-힣]{2,4})")
_NAME_WITH_TITLE_RE = re.compile(r"([가-힣]{2,4})\s*(?:명예교수|부교수|조교수|교수)")
_ENGLISH_NAME_RE = re.compile(r"[A-Z][A-Za-z, .-]{3,40}")
_FACULTY_TOKEN_RE = re.compile(r"[A-Za-z가-힣]{2,}")
_TITLE_HAS_TEXT_RE = re.compile(r"[가-힣A-Za-z]")


def open_url(url: str, *, timeout: int = 8) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Miho FacultyResearch", "Accept": "text/html, text/plain"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(500_000).decode("utf-8", errors="ignore")


def strip_html(raw: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", raw, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    return re.sub(r"[ \t]+", " ", html.unescape(text)).strip()


def search_naver_links(query: str, *, limit: int = 6) -> list[dict[str, str]]:
    url = "https://search.naver.com/search.naver?query=" + urllib.parse.quote(query)
    try:
        raw = open_url(url, timeout=8)
    except Exception:
        return []
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in _ANCHOR_LINK_RE.finditer(raw):
        href = html.unescape(match.group(1))
        host = urllib.parse.urlparse(href).netloc.lower()
        if any(blocked in host for blocked in ("naver.com", "pstatic.net", "instagram.com", "facebook.com", "jisikmall.com", "univ100.kr", "cafe.daum.net")):
            continue
        if href in seen:
            continue
        title = strip_html(match.group(2))[:120]
        context = strip_html(raw[match.start(): match.end() + 1400])[:320]
        seen.add(href)
        links.append({"title": title or href, "snippet": context, "url": href, "source": "naver_link"})
        if len(links) >= limit:
            break
    return links


def read_page_text(url: str) -> str:
    reader = "https://r.jina.ai/" + url
    texts: list[str] = []
    try:
        texts.append(open_url(reader, timeout=5))
    except Exception:
        pass
    try:
        raw = open_url(url, timeout=4)
        texts.append(strip_html(raw))
        for src in re.findall(r"<iframe\b[^>]*\bsrc=[\"']([^\"']+)[\"']", raw, flags=re.I):
            iframe_url = urllib.parse.urljoin(url, html.unescape(src))
            try:
                texts.append(open_url("https://r.jina.ai/" + iframe_url, timeout=5))
            except Exception:
                pass
    except Exception:
        pass
    if not texts:
        return ""
    return "\n".join(re.sub(r"\s+\n", "\n", text).strip() for text in texts if text.strip())


def _clean_name(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip(" -*·|")
    return text if text and text not in NOISE_WORDS else ""


def _english_variants(raw: str) -> list[str]:
    text = _clean_name(raw)
    if not text:
        return []
    variants: list[str] = []
    if "," in text:
        family, given = [part.strip() for part in text.split(",", 1)]
        given_family = f"{given} {family}".strip()
        spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", given_family)
        romanized = (
            spaced.replace("Kikwang", "Ki Kwang")
            .replace("Joohyung", "Joo Hyung")
            .replace("Miyoung", "Mi Young")
            .replace("Jihyun", "Ji Hyun")
            .replace("Hyunwook", "Hyun Wook")
        )
        variants.extend([romanized, spaced, given_family])
    variants.append(text)
    for value in list(variants):
        spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
        if spaced not in variants:
            variants.append(spaced)
    unique: list[str] = []
    for value in variants:
        if len(value) >= 4 and value not in unique:
            unique.append(value)
    return unique[:4]


def _is_korean_name(value: str) -> bool:
    return bool(_KOREAN_NAME_WITH_OPTION_RE.fullmatch(value.strip()))


def _clean_korean_name(value: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", value).strip()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _append_profile(
    profiles: list[dict[str, Any]],
    seen: set[str],
    *,
    korean: str = "",
    english: str = "",
    major: str = "",
    department: str = "",
) -> None:
    korean = _clean_korean_name(_clean_name(korean))
    english = _clean_name(english)
    major = _clean_name(major)
    key = korean or english
    if not key or key in seen or not major:
        return
    if english in {"Google Scholar", "ENGLISH", "CHA University", "About Major"}:
        return
    if english.startswith(("Department of ", "About ")):
        return
    if len(korean) > 4 or korean in NOISE_NAMES:
        return
    if any(part in major for part in NOISE_MAJOR_PARTS):
        return
    if not any(term in major.lower() for term in RESEARCH_TERMS):
        return
    if not korean and not english:
        return
    seen.add(key)
    profiles.append({
        "name": korean,
        "english_name": english,
        "english_variants": _english_variants(english),
        "major": major,
        "department": department,
    })


def _field_value(line: str, field: str) -> str:
    match = re.compile(_FIELD_VALUE_TEMPLATE.format(field=field)).search(line)
    return _clean_name(match.group(1)) if match else ""


def extract_faculty_profiles(text: str, *, department: str = "", limit: int = 8) -> list[dict[str, Any]]:
    lines = [_clean_name(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    compact = " | ".join(lines)
    for match in _FACULTY_ROW_RE.finditer(compact):
        _append_profile(
            profiles,
            seen,
            korean=match.group(1),
            major=match.group(2),
            department=department,
        )
        if len(profiles) >= limit:
            return profiles
    for idx, line in enumerate(lines):
        major = (
            _field_value(line, "전공")
            or _field_value(line, "주전공")
            or _field_value(line, "연구분야")
            or _field_value(line, "담당교과")
        )
        next_name = ""
        if not major:
            major_line = _PROFESSOR_MAJOR_LINE_RE.search(line)
            if major_line and idx + 1 < len(lines) and _is_korean_name(lines[idx + 1]):
                major = major_line.group(1)
                next_name = lines[idx + 1]
        if not major:
            continue
        window = lines[max(0, idx - 8):idx]
        korean = _clean_korean_name(next_name)
        english = ""
        for prev in reversed(window):
            if not korean:
                named = _NAME_LABEL_RE.search(prev) or _NAME_WITH_TITLE_RE.search(prev)
                if named:
                    korean = named.group(1)
                elif _KOREAN_NAME_RE.fullmatch(prev):
                    korean = prev
            if not english and _ENGLISH_NAME_RE.fullmatch(prev):
                english = prev
            if korean and english:
                break
        _append_profile(profiles, seen, korean=korean, english=english, major=major, department=department)
        if len(profiles) >= limit:
            break
    return profiles


def _paper_queries(university: str, profile: dict[str, Any]) -> list[str]:
    names = [profile.get("name", ""), *profile.get("english_variants", [])]
    major = str(profile.get("major") or "").strip()
    queries: list[str] = []
    for name in names:
        if not name:
            continue
        queries.append(f"{name} {university} {major} 논문")
        queries.append(f"{name} {major} research")
    return queries[:4]


def _matches_faculty(source: dict[str, str], profile: dict[str, Any]) -> bool:
    text_hay = " ".join(str(source.get(key) or "") for key in ("title", "snippet")).lower()
    name_hay = f"{text_hay} {source.get('url', '')}".lower()
    if not any(term in text_hay for term in RESEARCH_TERMS):
        return False
    names = [profile.get("name", ""), *profile.get("english_variants", [])]
    for name in names:
        if _KOREAN_NAME_RE.fullmatch(str(name)) and str(name) in name_hay:
            return True
        tokens = [t.lower() for t in _FACULTY_TOKEN_RE.findall(str(name))]
        if tokens and all(token in name_hay for token in tokens):
            return True
    return False


def _is_usable_paper_title(source: dict[str, Any], university: str) -> bool:
    title = re.sub(r"\s+", " ", str(source.get("title") or "")).strip()
    text_hay = f"{title} {source.get('snippet', '')}".lower()
    url = str(source.get("url") or "")
    if not title or len(title) < 12:
        return False
    if not any(term in text_hay for term in RESEARCH_TERMS):
        return False
    if title.startswith(("http://", "https://")) or "%" in title:
        return False
    blocked = ("›", "교수소개", "교수진", "저자", "authorDetail", "검색", "본문", "중고샵", "교보문고", "알라딘", "yes24", "학사안내", "교육과정")
    blocked_text = ("transport research", "교통혼잡", "차량 속도")
    if any(word in title or word in url for word in blocked) or any(word in text_hay for word in blocked_text):
        return False
    if " 논문" in title or title.endswith(" research") or university in title:
        return False
    return bool(_TITLE_HAS_TEXT_RE.search(title))


def paper_titles_from_bundle(bundle: dict[str, Any] | None, limit: int = 2) -> list[str]:
    if not isinstance(bundle, dict):
        return []
    titles: list[str] = []
    section = bundle.get("faculty_paper_sources")
    if not isinstance(section, list):
        return []
    def source_score(item: dict[str, Any]) -> int:
        hay = f"{item.get('title', '')} {item.get('snippet', '')} {item.get('faculty_major', '')}".lower()
        score = 0
        for term in ("biomechanics", "kinematics", "kinetics", "exercise", "physiology", "rehabilitation", "sport science"):
            score += 2 if term in hay else 0
        for term in ("운동역학", "운동 생리", "하지", "보행", "재활", "스포츠"):
            score += 2 if term in hay else 0
        return score
    for item in sorted(section, key=source_score, reverse=True):
        if isinstance(item, dict) and str(item.get("title") or "").strip():
            title = str(item["title"]).strip()
            titles.append(title)
    blocked = ("네이버", "검색 메뉴", "본문 영역", "지식iN", "인플루언서", "바로가기")
    seen: set[str] = set()
    unique: list[str] = []
    for title in titles:
        clean = re.sub(r"\s+", " ", title).replace("AI", "데이터 활용").strip()
        if not clean or clean in seen or any(word in clean for word in blocked):
            continue
        seen.add(clean)
        unique.append(clean[:56])
        if len(unique) >= limit:
            break
    return unique


def build_faculty_research(
    university: str,
    department: str,
    *,
    scholarly_search: Callable[[str], list[dict[str, str]]],
    max_faculty: int = 5,
) -> dict[str, Any]:
    links: list[dict[str, str]] = []
    for query in (
        f"{university} {department} 교수진",
        f"{university} {department} 교수소개",
        f"{university} {department} 교수",
        f"{university} {department} 연구실",
        f"{university} {department} faculty",
    ):
        for link in search_naver_links(query, limit=5):
            if link["url"] not in {item["url"] for item in links}:
                links.append(link)
    official_hints = OFFICIAL_HOST_HINTS.get(university, ())
    official_links = [
        link for link in links
        if official_hints and any(hint in urllib.parse.urlparse(link["url"]).netloc.lower() for hint in official_hints)
    ]
    if official_links:
        links = official_links
    def link_score(link: dict[str, str]) -> int:
        hay = f"{link.get('title', '')} {link.get('url', '')}"
        url = str(link.get("url") or "").lower()
        score = 0
        if department in hay:
            score += 6
        if "/professor" in url or "staf001001.page" in url:
            score += 10
        if "/curriculum" in url or "/notice" in url or "faculty/2026" in url:
            score -= 8
        if any(bad in url for bad in ("gstm.khu.ac.kr", "gradsport.khu.ac.kr", "cha.ac.kr")):
            score -= 12
        if any(word in hay.lower() for word in ("department/professor", "faculty", "professor03", "교수 소개", "교수소개", "연구실")):
            score += 4
        if "univOrgn" in hay or "대학조직" in hay:
            score -= 4
        return score
    links = sorted(links, key=link_score, reverse=True)
    page_texts = []
    for link in links[:4]:
        text = read_page_text(link["url"])
        if department in text or _contains_any(text, FACULTY_PAGE_HINTS):
            page_texts.append({"url": link["url"], "title": link["title"], "text": text})
    profiles: list[dict[str, Any]] = []
    for page in page_texts:
        profiles.extend(extract_faculty_profiles(page["text"], department=department, limit=max_faculty))
    unique_profiles = []
    seen: set[str] = set()
    for profile in profiles:
        key = profile.get("name") or profile.get("english_name")
        if key and key not in seen:
            seen.add(key)
            unique_profiles.append(profile)
    paper_sources: list[dict[str, str]] = []
    query_log: list[str] = []
    for profile in unique_profiles[:max_faculty]:
        for query in _paper_queries(university, profile):
            query_log.append(query)
            web_sources = [
                {"title": link.get("title", ""), "snippet": link.get("snippet", ""), "url": link.get("url", ""), "source": "naver_paper"}
                for link in search_naver_links(query, limit=3)
            ]
            for source in scholarly_search(query) + web_sources:
                if _matches_faculty(source, profile):
                    if not _is_usable_paper_title(source, university):
                        continue
                    enriched = dict(source)
                    enriched["faculty_name"] = str(profile.get("name") or profile.get("english_name") or "")
                    enriched["faculty_major"] = str(profile.get("major") or "")
                    paper_sources.append(enriched)
    deduped_sources: list[dict[str, str]] = []
    seen_sources: set[tuple[str, str]] = set()
    for source in paper_sources:
        key = (str(source.get("faculty_name") or ""), str(source.get("title") or ""))
        if key[1] and key not in seen_sources:
            seen_sources.add(key)
            deduped_sources.append(source)
    return {
        "faculty_profiles": unique_profiles[:max_faculty],
        "faculty_source_pages": [{"url": p["url"], "title": p["title"]} for p in page_texts],
        "faculty_paper_sources": deduped_sources[:12],
        "faculty_query_log": query_log,
    }


def recover_existing_faculty_research(result: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any]:
    if result.get("faculty_profiles") or not isinstance(existing, dict):
        return result
    cached_profiles = sanitize_faculty_profiles(existing.get("faculty_profiles") or [])
    if not cached_profiles:
        return result
    return {
        "faculty_profiles": cached_profiles,
        "faculty_source_pages": existing.get("faculty_source_pages") or [],
        "faculty_paper_sources": existing.get("faculty_paper_sources") or [],
        "faculty_query_log": existing.get("faculty_query_log") or [],
    }


def sanitize_faculty_profiles(profiles: list[Any]) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        name = str(profile.get("name") or profile.get("english_name") or "")
        major = str(profile.get("major") or "")
        if not name or name in NOISE_NAMES or any(part in major for part in NOISE_MAJOR_PARTS):
            continue
        if not any(term in major.lower() for term in RESEARCH_TERMS):
            continue
        if name in {"Google Scholar", "ENGLISH", "CHA University", "About Major", "SITEMAP", "Toggle navigation"}:
            continue
        if name.startswith(("Department of ", "About ", "Public Administration")):
            continue
        clean.append(dict(profile))
    return clean


def sanitize_faculty_paper_sources(sources: list[Any], university: str = "") -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for source in sources:
        if isinstance(source, dict) and _is_usable_paper_title(source, university):
            clean.append(dict(source))
    return clean


def bundle_sources_match_university(bundle: dict[str, Any], university: str) -> bool:
    hints = OFFICIAL_HOST_HINTS.get(university, ())
    pages = bundle.get("faculty_source_pages") or []
    if not hints or not pages:
        return True
    for page in pages:
        if not isinstance(page, dict):
            continue
        host = urllib.parse.urlparse(str(page.get("url") or "")).netloc.lower()
        if not any(hint in host for hint in hints):
            return False
    return True
