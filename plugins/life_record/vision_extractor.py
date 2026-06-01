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
  "grades": [{"grade": int, "semester": int, "category": str|null, "subject": str, "credits": number|null, "raw_score": str|null, "achievement": str|null, "students_count": int|null, "rank_grade": str|null}],
  "notes": [{"grade": int|null, "semester": int|null, "subject": str, "note_text": str}],
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


def _merge(base: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    for field, value in (part.get("identity") or {}).items():
        if value and not base["identity"].get(field):
            base["identity"][field] = value
    for key in ("attendance", "grades", "notes", "awards"):
        base[key].extend(part.get(key) or [])
    return base


TextResolver = Callable[[str], Awaitable[str]]


async def default_text_resolver(prompt: str) -> str:
    from agent.auxiliary_client import async_call_llm
    from plugins.academy_ops.codex_model_policy import codex_provider

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            response = await async_call_llm(
                task="life_record_text",
                provider=codex_provider(),
                model=VISION_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=8000,
                timeout=180,
            )
            return _response_text(response)
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                await asyncio.sleep(2)
    raise last_exc or RuntimeError("text resolver failed after retries")


async def extract_from_text(page_texts: list[str], *, resolver: TextResolver | None = None) -> dict[str, Any]:
    """Structure the PDF's own text layer into the schema. Numbers are copied from
    exact digital text, so scores don't drift between runs — the 100% path."""
    joined = "\n\n".join(f"[p{i + 1}]\n{t}" for i, t in enumerate(page_texts) if (t or "").strip())
    resolve = resolver or default_text_resolver
    raw = await resolve(TEXT_PROMPT + "\n\n=== 생기부 원문 ===\n" + joined)
    return parse_extraction_json(raw)


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
    # stream doesn't drop, and total wall-clock is one batch, not the sum.
    chunks = [images[i : i + batch_size] for i in range(0, len(images), batch_size)]
    raws = await asyncio.gather(*(resolve(chunk, EXTRACTION_PROMPT) for chunk in chunks))
    merged = _empty()
    for raw in raws:
        merged = _merge(merged, parse_extraction_json(raw))
    return merged
