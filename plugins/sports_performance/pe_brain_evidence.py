"""PE-brain paper evidence packs for sports performance coaching."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable

from miho_constants import get_miho_home

from .catalog import normalize_exercise
from .pe_brain_terms import (
    ALLOWED_PE_BRAIN_CATEGORIES,
    EXERCISE_TERMS,
    MENTAL_TERMS,
    OFF_DOMAIN_TERMS,
    SPORTS_TERMS,
)

PE_BRAIN_PAPERS_ENDPOINT = "https://pe-brain.etlab.kr/api/papers/"
PE_BRAIN_REF_PREFIX = "pe_brain:"
_DEFAULT_LIMIT = 8
_MAX_LIMIT = 20
_CACHE_TTL_SECONDS = 60 * 60 * 24


def pe_brain_evidence_tool_handler(args: dict[str, Any] | None = None, **_: Any) -> str:
    return json.dumps(build_pe_brain_evidence_response(args or {}), ensure_ascii=False)


def build_pe_brain_evidence_response(args: dict[str, Any]) -> dict[str, Any]:
    action = str(args.get("action") or "search").strip().lower()
    if action not in {"search", "sync", "list"}:
        return {"ok": False, "errors": ["action은 search, sync, list 중 하나여야 한다."]}
    state = load_pe_brain_evidence_state(force_refresh=action == "sync" or bool(args.get("refresh")))
    packs = state["packs"]
    selected = select_evidence_packs(
        packs,
        exercise=args.get("exercise"),
        query=args.get("query"),
        category=args.get("category"),
        include_review_required=bool(args.get("include_review_required")),
        limit=_bounded_limit(args.get("limit")),
    )
    return {
        "ok": True,
        "action": action,
        "source": "pe_brain",
        "endpoint": PE_BRAIN_PAPERS_ENDPOINT,
        "total_packs": len(packs),
        "quality_counts": _quality_counts(packs),
        "packs": selected,
        "source_info": state["source_info"],
        "rag_policy": {
            "current_mode": "evidence_pack_first",
            "reason": "full-text chunk export가 확인되기 전까지 accepted evidence pack만 코칭 근거로 사용한다.",
            "future_mode": "rag_retrieval_after_chunk_export",
        },
        "warnings": _source_warnings(state["source_info"], packs),
    }


def load_pe_brain_evidence_state(*, force_refresh: bool = False) -> dict[str, Any]:
    papers, source_info = _load_papers_with_cache(force_refresh=force_refresh)
    return {"papers": papers, "packs": build_evidence_packs(papers), "source_info": source_info}


def load_pe_brain_evidence_packs(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    return load_pe_brain_evidence_state(force_refresh=force_refresh)["packs"]


def build_evidence_packs(papers: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    packs = [_build_pack(paper) for paper in papers if isinstance(paper, dict)]
    return sorted(packs, key=_pack_sort_key)


def select_evidence_packs(
    packs: Iterable[dict[str, Any]],
    *,
    exercise: Any = None,
    query: Any = None,
    category: Any = None,
    include_review_required: bool = False,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    exercise_key = _exercise_key(exercise)
    category_text = str(category or "").strip().lower()
    query_terms = [part for part in str(query or "").lower().split() if part]
    selected: list[dict[str, Any]] = []
    for pack in packs:
        if pack.get("quality_status") != "accepted" and not include_review_required:
            continue
        if exercise_key and exercise_key not in pack.get("exercise_keys", ()):
            continue
        if category_text and pack.get("category") != category_text:
            continue
        haystack = f"{pack.get('title', '')} {pack.get('summary', '')}".lower()
        if query_terms and not all(term in haystack for term in query_terms):
            continue
        selected.append(pack)
    return sorted(selected, key=_pack_sort_key)[:limit]


def resolve_pe_brain_evidence_refs(refs: Iterable[str], *, exercise_key: str) -> dict[str, Any]:
    requested = [str(ref).strip() for ref in refs if str(ref).strip()]
    if not requested:
        return {"status": "not_requested", "accepted_refs": [], "invalid_refs": [], "accepted_packs": [], "unmanaged_refs": []}
    packs = load_pe_brain_evidence_packs()
    by_id = {pack["id"]: pack for pack in packs}
    accepted_refs: list[str] = []
    accepted_packs: list[dict[str, Any]] = []
    invalid_refs: list[dict[str, str]] = []
    unmanaged_refs: list[str] = []
    for ref in requested:
        if not ref.startswith(PE_BRAIN_REF_PREFIX):
            invalid_refs.append({"ref": ref, "reason": "구조화 검증되지 않은 외부 근거 ref는 코칭 근거로 쓰지 않는다."})
            continue
        pack = by_id.get(ref)
        if pack is None:
            invalid_refs.append({"ref": ref, "reason": "PE-brain 근거팩을 찾을 수 없다."})
            continue
        reason = _invalid_ref_reason(pack, exercise_key)
        if reason:
            invalid_refs.append({"ref": ref, "reason": reason})
            continue
        accepted_refs.append(ref)
        accepted_packs.append(_public_pack(pack))
    return {
        "status": "invalid" if invalid_refs else "valid",
        "accepted_refs": accepted_refs,
        "invalid_refs": invalid_refs,
        "accepted_packs": accepted_packs,
        "unmanaged_refs": unmanaged_refs,
    }


def _build_pack(raw: dict[str, Any]) -> dict[str, Any]:
    paper_id = _text(raw.get("id"))
    title = _text(raw.get("title"))
    summary = _text(raw.get("summary"))
    category = _text(raw.get("category")).lower()
    status = _text(raw.get("status")).lower()
    chunk_count = _safe_int(raw.get("chunk_count"))
    created_at = _text(raw.get("created_at"))
    corpus = f"{title} {summary}".lower()
    exercise_keys = _exercise_tags(corpus)
    domain_tags = _domain_tags(corpus, category, exercise_keys)
    quality_status, quality_reasons = _quality_status(
        category=category,
        status=status,
        chunk_count=chunk_count,
        summary=summary,
        domain_tags=domain_tags,
        exercise_keys=exercise_keys,
        corpus=corpus,
    )
    return {
        "id": f"{PE_BRAIN_REF_PREFIX}{paper_id}",
        "source": "pe_brain",
        "paper_id": paper_id,
        "title": title,
        "category": category,
        "status": status,
        "chunk_count": chunk_count,
        "summary": summary,
        "created_at": created_at,
        "evidence_depth": "summary_only" if summary else "metadata_only",
        "domain_tags": domain_tags,
        "exercise_keys": exercise_keys,
        "quality_status": quality_status,
        "quality_reasons": quality_reasons,
    }


def _quality_status(
    *,
    category: str,
    status: str,
    chunk_count: int,
    summary: str,
    domain_tags: list[str],
    exercise_keys: list[str],
    corpus: str,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    off_domain_hits = [term for term in OFF_DOMAIN_TERMS if term.lower() in corpus]
    if off_domain_hits:
        return "rejected", ["오프도메인 논문이다.", *[f"감지어: {hit}" for hit in off_domain_hits[:3]]]
    if category not in ALLOWED_PE_BRAIN_CATEGORIES:
        reasons.append("PE-brain physical/mental 카테고리가 아니다.")
    if status and status != "completed":
        reasons.append("PE-brain 처리 상태가 completed가 아니다.")
    if chunk_count <= 0:
        reasons.append("논문 chunk_count가 없어 원문 근거 추적이 불안정하다.")
    if not summary:
        reasons.append("요약이 없어 최종 코칭 근거로 바로 쓰지 않는다.")
    if not domain_tags:
        reasons.append("체대입시 운동/멘탈관리 관련성이 충분히 확인되지 않았다.")
    if category == "physical" and not exercise_keys:
        reasons.append("physical 논문은 종목별 운동 태그가 있어야 accepted가 된다.")
    if category == "mental" and "mental_performance" not in domain_tags:
        reasons.append("mental 논문은 스포츠 멘탈 수행 태그가 있어야 accepted가 된다.")
    return ("review_required", reasons) if reasons else ("accepted", ["accepted_summary_domain_match"])


def _invalid_ref_reason(pack: dict[str, Any] | None, exercise_key: str) -> str | None:
    if pack is None:
        return "PE-brain 근거팩을 찾을 수 없다."
    if pack.get("quality_status") != "accepted":
        return "accepted 상태의 PE-brain 근거팩이 아니다."
    exercise_keys = set(pack.get("exercise_keys") or [])
    domain_tags = set(pack.get("domain_tags") or [])
    if exercise_key in exercise_keys:
        return None
    if pack.get("category") == "mental" and "mental_performance" in domain_tags:
        return None
    return "요청 종목과 PE-brain 근거팩 태그가 맞지 않는다."


def _domain_tags(corpus: str, category: str, exercise_keys: list[str]) -> list[str]:
    tags = set(exercise_keys)
    if any(term in corpus for term in MENTAL_TERMS):
        tags.add("mental_performance")
    if category == "physical" and any(term in corpus for term in SPORTS_TERMS):
        tags.add("sports_science")
    return sorted(tags)


def _exercise_tags(corpus: str) -> list[str]:
    return sorted(key for key, terms in EXERCISE_TERMS.items() if any(term in corpus for term in terms))


def _load_papers_with_cache(*, force_refresh: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cached_payload = _read_cache_payload()
    if cached_payload and not force_refresh and not _cache_stale(cached_payload):
        return _cache_papers(cached_payload), _cache_info(cached_payload, status="cache_hit", source_error="")
    try:
        papers = _fetch_pe_brain_papers(PE_BRAIN_PAPERS_ENDPOINT, timeout=8)
    except (OSError, TimeoutError, ValueError, urllib.error.URLError) as exc:
        if cached_payload:
            return _cache_papers(cached_payload), _cache_info(
                cached_payload,
                status="fallback_cache",
                source_error=type(exc).__name__,
            )
        return [], {
            "status": "failed_empty",
            "source": "none",
            "fetched_at": 0,
            "stale": True,
            "source_error": type(exc).__name__,
        }
    _write_cache(papers)
    return papers, {
        "status": "fetched",
        "source": "api",
        "fetched_at": int(time.time()),
        "stale": False,
        "source_error": "",
    }


def _fetch_pe_brain_papers(endpoint: str, *, timeout: int) -> list[dict[str, Any]]:
    request = urllib.request.Request(endpoint, headers={"Accept": "application/json", "User-Agent": "miho-agent"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - internal ET endpoint
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("PE-brain papers API must return a list")
    return [item for item in payload if isinstance(item, dict)]


def _read_cache_payload() -> dict[str, Any] | None:
    path = _cache_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_cache(papers: list[dict[str, Any]]) -> None:
    path = _cache_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        payload = {"source": "pe_brain", "fetched_at": int(time.time()), "papers": papers}
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    except OSError:
        return


def _cache_papers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    papers = payload.get("papers")
    return [item for item in papers or [] if isinstance(item, dict)]


def _cache_info(payload: dict[str, Any], *, status: str, source_error: str) -> dict[str, Any]:
    fetched_at = _safe_int(payload.get("fetched_at"))
    return {
        "status": status,
        "source": "cache",
        "fetched_at": fetched_at,
        "stale": _cache_stale(payload),
        "source_error": source_error,
    }


def _cache_stale(payload: dict[str, Any]) -> bool:
    fetched_at = _safe_int(payload.get("fetched_at"))
    if fetched_at <= 0:
        return True
    return time.time() - fetched_at > _CACHE_TTL_SECONDS


def _cache_path() -> Path:
    return get_miho_home() / "sports_performance" / "pe_brain_papers.json"


def _quality_counts(packs: Iterable[dict[str, Any]]) -> dict[str, int]:
    counts = {"accepted": 0, "review_required": 0, "rejected": 0}
    for pack in packs:
        key = str(pack.get("quality_status") or "")
        if key in counts:
            counts[key] += 1
    return counts


def _source_warnings(source_info: dict[str, Any], packs: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    if not packs:
        warnings.append("PE-brain 논문 목록이 비어 있어 기본 운동분석 근거 정책으로 계속 진행한다.")
    if source_info.get("source_error"):
        warnings.append("PE-brain API 동기화에 실패해 캐시 또는 기본 정책으로 계속 진행한다.")
    if source_info.get("stale"):
        warnings.append("PE-brain 캐시가 오래됐다. sync를 다시 시도해야 최신 논문을 반영한다.")
    return warnings


def _public_pack(pack: dict[str, Any]) -> dict[str, Any]:
    return {
        key: pack[key]
        for key in (
            "id",
            "source",
            "paper_id",
            "title",
            "category",
            "evidence_depth",
            "domain_tags",
            "exercise_keys",
            "quality_status",
        )
        if key in pack
    }


def _pack_sort_key(pack: dict[str, Any]) -> tuple[int, str]:
    rank = {"accepted": 0, "review_required": 1, "rejected": 2}.get(str(pack.get("quality_status")), 3)
    return (rank, str(pack.get("created_at") or ""))


def _exercise_key(value: Any) -> str:
    exercise = normalize_exercise(value)
    return str(exercise["key"]) if exercise else ""


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _bounded_limit(value: Any) -> int:
    limit = _safe_int(value) or _DEFAULT_LIMIT
    return max(1, min(limit, _MAX_LIMIT))


def _text(value: Any) -> str:
    return str(value or "").strip()
