"""Vision-based structured extraction for Korean school life records (생기부).

Renders PDF pages to images and asks a multimodal model (codex gpt-5.5) to return
structured JSON. This replaces the brittle PyMuPDF-text + regex parser: a scanned
PDF with no text layer is read just like a normal one, because the model sees the
page image directly (PoC-confirmed 2026-06-01).

The model call is injected (``VisionResolver``) so unit tests use a fake and only
the opt-in live test hits codex.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from typing import Any, Awaitable, Callable

VisionResolver = Callable[[list[str], str], Awaitable[str]]

VISION_MODEL = "gpt-5.5"
EXTRACT_VERSION = "codex_vision_gpt5.5_v1"

_SCHEMA = """JSON 스키마:
{
  "identity": {"name": str|null, "school_name": str|null, "birth6": "YYMMDD"|null, "class_no": str|null, "student_no": str|null},
  "attendance": [{"grade": int, "school_days": int|null, "absence": str|null, "late": str|null, "early_leave": str|null, "special_note": str|null}],
  "grades": [{"grade": int, "semester": int, "category": str|null, "subject": str, "credits": number|null, "raw_score": str|null, "achievement": str|null, "students_count": int|null, "rank_grade": str|null, "course_type": "진로선택"|"일반선택"|null}],
  // course_type: 생기부에서 '진로 선택 과목' 표(섹션)에 속한 과목은 "진로선택", 공통/일반선택 과목은 "일반선택"으로 구분한다. 대학 산식이 진로선택만 성취도→등급 환산해 반영하므로(일반선택 성취도평가 과목은 제외) 반드시 구분한다. 석차등급이 있으면 일반선택이다.
  "notes": [{"grade": int|null, "semester": int|null, "subject": str, "note_text": str}],
  // notes에는 과목별 세부능력 및 특기사항뿐 아니라 창의적 체험활동상황(자율/동아리/진로/봉사), 행동특성 및 종합의견도 포함한다. 이때 subject는 "창체: 자율활동", "창체: 동아리활동", "창체: 진로활동", "행동특성 및 종합의견"처럼 구분한다.
  "awards": [{"grade": int|null, "title": str, "awarded_at": str|null, "issuer": str|null}]
}
오직 JSON만 출력. 설명/코드펜스 금지."""

EXTRACTION_PROMPT = (
    "너는 한국 고등학교 학교생활기록부(생기부) 구조화 추출 전문가야.\n"
    "주어진 페이지 이미지들을 보고 아래 JSON 스키마로 정확히 추출해.\n"
    "숫자(점수/석차/일수)와 고유명사(이름/학교/과목)는 한 글자도 틀리지 마. 안 보이면 null.\n"
    "개인정보 보호: 주민등록번호는 앞 6자리(생년월일 YYMMDD)만, 뒷자리는 절대 출력하지 마.\n\n"
    + _SCHEMA
)

# Text-layer path: when the PDF has a real text layer, the scores/numbers are
# already exact digital text — no OCR guessing. The model only has to restructure
# the (line-break-mangled) text, copying numbers verbatim. This is the 100%-accurate
# path for non-scanned 생기부 (vision is the fallback for scans like 김동혁).
TEXT_PROMPT = (
    "아래는 한국 고등학교 생활기록부(생기부) PDF에서 추출한 원문 텍스트다.\n"
    "줄바꿈과 표가 흐트러져 있어도 의미로 재구성해 아래 JSON 스키마로 정확히 추출해.\n"
    "점수·숫자·과목명·날짜는 원문에 있는 그대로 옮겨라(추측·변형·반올림 절대 금지). 안 보이면 null.\n"
    "개인정보: 주민등록번호는 앞 6자리(생년월일)만, 뒷자리는 절대 출력하지 마.\n\n"
    + _SCHEMA
)


def has_text_layer(page_texts: list[str], *, min_chars: int = 400) -> bool:
    """True when the PDF carries a real text layer (scores are exact digital text,
    so use the text path). A scanned PDF returns ~0 chars → vision fallback."""
    return sum(len(t or "") for t in page_texts) >= min_chars


async def default_codex_resolver(images: list[str], prompt: str) -> str:
    from agent.auxiliary_client import async_call_llm
    from plugins.academy_ops.codex_model_policy import codex_provider

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for url in images:
        content.append({"type": "image_url", "image_url": {"url": url}})
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = await async_call_llm(
                task="life_record_vision",
                provider=codex_provider(),
                model=VISION_MODEL,
                messages=[{"role": "user", "content": content}],
                temperature=0,
                max_tokens=4000,
                timeout=180,
            )
            return _response_text(response)
        except Exception as exc:
            # codex streaming can drop mid-response ("peer closed connection /
            # incomplete chunked read") on a large multi-image request — retry.
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(2)
    raise last_exc or RuntimeError("vision resolver failed after retries")


def _response_text(response: Any) -> str:
    try:
        return response.choices[0].message.content or ""
    except Exception:
        if isinstance(response, str):
            return response
        return str(getattr(response, "content", "") or "")


def to_data_url(png_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")


def parse_extraction_json(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _empty()
    return _normalize(payload)


def _empty() -> dict[str, Any]:
    return {"identity": {}, "attendance": [], "grades": [], "notes": [], "awards": []}


def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
    out = _empty()
    if not isinstance(payload, dict):
        return out
    ident = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
    out["identity"] = {
        "name": _s(ident.get("name")),
        "school_name": _s(ident.get("school_name")),
        "birth6": _mask_birth(ident.get("birth6")),
        "class_no": _s(ident.get("class_no")),
        "student_no": _s(ident.get("student_no")),
    }
    for key in ("attendance", "grades", "notes", "awards"):
        value = payload.get(key)
        out[key] = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    return out


def _s(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _mask_birth(value: Any) -> str | None:
    """Keep only the first 6 digits (생년월일); never store the back digits."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))[:6]
    return digits or None


DEFAULT_BATCH = 5
# Cap how many image batches are in flight at once. Unbounded asyncio.gather over
# a large 생기부 would hold every batch's base64 in memory and hammer the codex
# stream simultaneously (P2-6). 3 keeps peak memory/connections bounded.
MAX_CONCURRENT_BATCHES = 3


def _merge(base: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    for field, value in (part.get("identity") or {}).items():
        if value and not base["identity"].get(field):
            base["identity"][field] = value
    for key in ("attendance", "grades", "notes", "awards"):
        base[key].extend(part.get(key) or [])
    return base


PHOTO_BBOX_PROMPT = (
    "이 생기부 첫 페이지에서 학생 증명사진(얼굴 사진) 영역의 위치만 0~1 비율로 알려줘. "
    'JSON 한 줄로: {"x0":좌, "y0":상, "x1":우, "y1":하}. 증명사진이 없으면 {} 만 출력.'
)


async def locate_id_photo(image_data_url: str, *, resolver: "VisionResolver | None" = None) -> dict[str, float] | None:
    """Ask vision for the ID-photo bbox (0~1 ratios) on the first page, so a scanned
    PDF (whole page = one image) can be cropped down to just the photo."""
    resolve = resolver or default_codex_resolver
    raw = await resolve([image_data_url], PHOTO_BBOX_PROMPT)
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not all(k in payload for k in ("x0", "y0", "x1", "y1")):
        return None
    try:
        box = {k: float(payload[k]) for k in ("x0", "y0", "x1", "y1")}
    except (TypeError, ValueError):
        return None
    # sanity: ordered, within [0,1], non-trivial area
    if not (0 <= box["x0"] < box["x1"] <= 1 and 0 <= box["y0"] < box["y1"] <= 1):
        return None
    return box


TextResolver = Callable[[str], Awaitable[str]]

TEXT_LLM_MAX_TOKENS = 16000
TEXT_LLM_TIMEOUT_SECONDS = 180
TEXT_LLM_ATTEMPTS = 3
MHTML_TEXT_LLM_TIMEOUT_SECONDS = 240


async def default_text_resolver(
    prompt: str,
    *,
    attempts: int = TEXT_LLM_ATTEMPTS,
    timeout: int = TEXT_LLM_TIMEOUT_SECONDS,
    max_tokens: int = TEXT_LLM_MAX_TOKENS,
) -> str:
    from agent.auxiliary_client import async_call_llm
    from plugins.academy_ops.codex_model_policy import codex_provider

    last_exc: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            response = await async_call_llm(
                task="life_record_text",
                provider=codex_provider(),
                model=VISION_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            return _response_text(response)
        except Exception as exc:
            last_exc = exc
            if attempt < max(1, attempts) - 1:
                await asyncio.sleep(2)
    raise last_exc or RuntimeError("text resolver failed after retries")


_ORIGINAL_DEFAULT_TEXT_RESOLVER = default_text_resolver


async def extract_from_text(page_texts: list[str], *, resolver: TextResolver | None = None) -> dict[str, Any]:
    """Structure the PDF's own text layer into the schema. Numbers are copied from
    exact digital text, so scores don't drift between runs — the 100% path."""
    joined = "\n\n".join(f"[p{i + 1}]\n{t}" for i, t in enumerate(page_texts) if (t or "").strip())
    resolve = resolver or default_text_resolver
    raw = await resolve(TEXT_PROMPT + "\n\n=== 생기부 원문 ===\n" + joined)
    parsed = parse_extraction_json(raw)
    return _enrich_from_neis_text(parsed, joined)


async def extract_from_mhtml_text(page_texts: list[str], *, resolver: TextResolver | None = None) -> dict[str, Any]:
    """One bounded model pass for text-rich NEIS MHTML.

    MHTML already has exact source text, so repeated long model retries only add
    latency. Accuracy comes from reconciling this single model pass with the
    deterministic source extractor in the service layer.
    """
    joined = "\n\n".join(f"[p{i + 1}]\n{t}" for i, t in enumerate(page_texts) if (t or "").strip())
    prompt = TEXT_PROMPT + "\n\n=== 생기부 원문 ===\n" + joined
    if resolver is None and default_text_resolver is _ORIGINAL_DEFAULT_TEXT_RESOLVER:
        raw = await default_text_resolver(prompt, attempts=1, timeout=MHTML_TEXT_LLM_TIMEOUT_SECONDS)
    else:
        resolve = resolver or default_text_resolver
        raw = await resolve(prompt)
    parsed = parse_extraction_json(raw)
    return _enrich_from_neis_text(parsed, joined)


def _enrich_from_neis_text(parsed: dict[str, Any], text: str) -> dict[str, Any]:
    """Best-effort deterministic recovery for NEIS+ text/MHTML exports.

    The LLM text pass is good for tabular grades, but Chrome-saved NEIS+ MHTML
    can be long enough that narrative fields (창체/세특/행특) are skipped. The
    source text is already exact Korean, so recover obvious labels locally and
    merge them into the same notes table.
    """
    text = text or ""
    identity = parsed.setdefault("identity", {})
    if not identity.get("name"):
        name = _first_match(text, r"(?:^|\n)성명\s*\n\s*([^\n]+)") or _first_match(text, r"title=\"([^\"]+) 님 정보") or _first_match(text, r"\n\s*([가-힣]{2,5}) 님")
        if name:
            identity["name"] = name.strip()
    if not identity.get("school_name"):
        school = _first_match(text, r"\d{4}년\s*\d{2}월\s*\d{2}일\s+([^\n]*고등학교)\s+제\d학년\s+입학")
        if school:
            identity["school_name"] = school.strip()

    notes = list(parsed.get("notes") or [])
    notes.extend(_extract_activity_notes(text))
    notes.extend(_extract_behavior_notes(text))
    notes.extend(_extract_subject_notes(text))
    parsed["notes"] = _dedupe_notes(notes)
    return parsed


def _first_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, flags=re.M)
    return match.group(1).strip() if match else None


def _section_between(text: str, start: str, end: str | None = None, *, occurrence: int = 2) -> str:
    positions = [m.start() for m in re.finditer(re.escape(start), text)]
    if len(positions) < occurrence:
        return ""
    s = positions[occurrence - 1]
    e = len(text)
    if end:
        end_match = re.search(re.escape(end), text[s + 1 :])
        if end_match:
            e = s + 1 + end_match.start()
    return text[s:e]


def _extract_activity_notes(text: str) -> list[dict[str, Any]]:
    section = _section_between(text, "6. 창의적 체험활동상황", "7. 교과학습발달상황", occurrence=2)
    if not section:
        return []
    stop = section.find("< 봉사활동실적 >")
    if stop >= 0:
        section = section[:stop]
    lines = [line.strip() for line in section.splitlines()]
    rows: list[dict[str, Any]] = []
    current_grade: int | None = None
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.fullmatch(r"[123]", line):
            current_grade = int(line)
            i += 1
            continue
        if line in {"자율활동", "동아리활동", "진로활동"} and current_grade is not None:
            area = line
            i += 1
            if i < len(lines) and re.fullmatch(r"\d+", lines[i]):
                i += 1
            body: list[str] = []
            while i < len(lines):
                nxt = lines[i]
                if re.fullmatch(r"[123]", nxt) or nxt in {"자율활동", "동아리활동", "진로활동"}:
                    break
                if nxt:
                    body.append(nxt)
                i += 1
            note = _clean_note_text("\n".join(body))
            if note:
                rows.append({"grade": current_grade, "semester": None, "subject": f"창체: {area}", "note_text": note})
            continue
        i += 1
    return rows


def _extract_behavior_notes(text: str) -> list[dict[str, Any]]:
    section = _section_between(text, "9. 행동특성 및 종합의견", None, occurrence=2)
    if not section:
        return []
    footer = section.find("개인정보처리방침")
    if footer >= 0:
        section = section[:footer]
    pattern = re.compile(r"(?:^|\n)\s*(\d)\s*\n(.*?)(?=\n\s*\d\s*\n|\Z)", re.S)
    rows: list[dict[str, Any]] = []
    for grade, body in pattern.findall(section):
        note = _clean_note_text(body)
        if note and "행동특성 및 종합의견" not in note[:50] and "학년" not in note[:20]:
            rows.append({"grade": int(grade), "semester": None, "subject": "행동특성 및 종합의견", "note_text": note})
    return rows


_SUBJECT_NOTE_LABEL = re.compile(r"(?:^|\n)([가-힣A-Za-zⅠⅡⅢ0-9·・\s]{1,35}):\s*(.*?)(?=\n[가-힣A-Za-zⅠⅡⅢ0-9·・\s]{1,35}:\s|\n\s*<\s|\n\s*\d학년\s|\n\s*8\. 독서|\n\s*9\. 행동|\Z)", re.S)
_SUBJECT_EXCLUDE = {"희망분야", "이수학점 합계", "COPYRIGHT"}


def _extract_subject_notes(text: str) -> list[dict[str, Any]]:
    section = _section_between(text, "7. 교과학습발달상황", "9. 행동특성 및 종합의견", occurrence=2)
    if not section:
        return []
    rows: list[dict[str, Any]] = []
    for match in _SUBJECT_NOTE_LABEL.finditer(section):
        subject = re.sub(r"\s+", " ", match.group(1)).strip()
        subject = re.sub(r"^세부능력 및 특기사항\s+", "", subject).strip()
        if subject in _SUBJECT_EXCLUDE or len(subject) > 25:
            continue
        note = _clean_note_text(match.group(2))
        if not note or len(note) < 20:
            continue
        before = section[: match.start()]
        grade_match = list(re.finditer(r"(\d)학년", before))
        grade = int(grade_match[-1].group(1)) if grade_match else None
        rows.append({"grade": grade, "semester": None, "subject": subject, "note_text": note})
    return rows


def _clean_note_text(value: str) -> str:
    text = re.sub(r"\n+", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _dedupe_notes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, str, str]] = set()
    for row in rows:
        subject = str(row.get("subject") or "").strip()
        note = str(row.get("note_text") or "").strip()
        if not subject or not note:
            continue
        key = (row.get("grade"), row.get("semester"), subject, note[:120])
        if key in seen:
            continue
        seen.add(key)
        clean = dict(row)
        clean["subject"] = subject
        clean["note_text"] = note
        out.append(clean)
    return out


async def extract_life_record(
    images: list[str], *, resolver: VisionResolver | None = None, batch_size: int = DEFAULT_BATCH
) -> dict[str, Any]:
    """One vision pass over all pages -> structured dict.

    Pages are sent in batches (default 8) and merged, so a 28-page 생기부 stays
    under the request-size limit instead of shipping ~26MB of base64 at once.
    """
    resolve = resolver or default_codex_resolver
    if len(images) <= batch_size:
        return parse_extraction_json(await resolve(images, EXTRACTION_PROMPT))
    # Smaller batches in parallel — each request stays light enough that the codex
    # stream doesn't drop. A semaphore caps how many are in flight at once so a
    # large 생기부 doesn't hold every batch's base64 in memory simultaneously.
    chunks = [images[i : i + batch_size] for i in range(0, len(images), batch_size)]
    sem = asyncio.Semaphore(MAX_CONCURRENT_BATCHES)

    async def _resolve_one(chunk: list[str]) -> str:
        async with sem:
            return await resolve(chunk, EXTRACTION_PROMPT)

    raws = await asyncio.gather(*(_resolve_one(chunk) for chunk in chunks))
    merged = _empty()
    for raw in raws:
        merged = _merge(merged, parse_extraction_json(raw))
    return merged
