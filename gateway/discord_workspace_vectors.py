"""Vector indexing and hybrid retrieval for Discord workspace memory."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from collections import deque
from pathlib import Path
from typing import Any

from utils import atomic_json_write
from gateway.discord_workspace_paths import count_lines, path_lock

logger = logging.getLogger(__name__)

# Track rag_dirs we've already warned about so a keyless install (hash
# fallback on every query) doesn't flood the log — one warning per dir/process.
_warned_hash_dirs: set[str] = set()


_LOCAL_EMBEDDING_DIMENSIONS = 256
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣_]{2,}")
_KOREAN_PARTICLE_RE = re.compile(r"(으로|에서|에게|한테|부터|까지|처럼|보다|은|는|이|가|을|를|로|에|와|과|도|만|랑)$")
_SPACE_RE = re.compile(r"\s+")
_DEFAULT_MAX_SCAN_RECORDS = 2500
_HASH_METHOD = "local-hash-v1"

# Hybrid retrieval tuning. These were inline magic numbers; named here and
# overridable via config (discord.workspace_rag.retrieval) so search quality
# can be tuned without editing code — matching how the semantic-intent
# threshold is configurable. Keys mirror the dict returned by _retrieval_tuning.
_DEFAULT_RETRIEVAL_TUNING: dict[str, float] = {
    "semantic_weight": 0.65,
    "keyword_weight": 0.35,
    "keyword_coverage_weight": 0.85,
    "keyword_precision_weight": 0.15,
    "min_semantic_no_keyword": 0.18,
    "min_keyword": 0.15,
    "min_semantic": 0.12,
    "long_query_terms": 3,
    "long_query_min_keyword": 0.5,
    "long_query_min_semantic": 0.18,
}


def _retrieval_tuning() -> dict[str, float]:
    """Return hybrid-retrieval weights/thresholds, config-overridable.

    Falls back to _DEFAULT_RETRIEVAL_TUNING; any subset of keys may be
    overridden under config discord.workspace_rag.retrieval.
    """
    tuning = dict(_DEFAULT_RETRIEVAL_TUNING)
    try:
        from miho_cli.config import load_config

        cfg = load_config()
        override = cfg.get("discord", {}).get("workspace_rag", {}).get("retrieval", {})
        if isinstance(override, dict):
            for key in tuning:
                if key in override:
                    try:
                        tuning[key] = float(override[key])
                    except (TypeError, ValueError):
                        pass
    except Exception:
        pass
    return tuning


def _embedding_settings() -> tuple[str, str]:
    provider = os.getenv("MIHO_DISCORD_EMBEDDING_PROVIDER", "").strip().lower()
    model = os.getenv("MIHO_DISCORD_EMBEDDING_MODEL", "").strip()
    try:
        from miho_cli.config import load_config

        cfg = load_config()
        rag_cfg = cfg.get("discord", {}).get("workspace_rag", {})
        if isinstance(rag_cfg, dict):
            provider = provider or str(rag_cfg.get("embedding_provider") or "").lower()
            model = model or str(rag_cfg.get("embedding_model") or "").strip()
    except Exception:
        pass
    if provider not in {"auto", "voyage", "openai", "local"}:
        provider = "auto"
    return provider or "auto", model


def _max_scan_records() -> int:
    raw = os.getenv("MIHO_DISCORD_RAG_MAX_SCAN_RECORDS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    try:
        from miho_cli.config import load_config

        cfg = load_config()
        rag_cfg = cfg.get("discord", {}).get("workspace_rag", {})
        configured = str(rag_cfg.get("max_scan_records") or "").strip()
        if configured.isdigit() and int(configured) > 0:
            return int(configured)
    except Exception:
        pass
    return _DEFAULT_MAX_SCAN_RECORDS


def _read_recent_vector_lines(vector_path: Path, limit: int) -> list[str]:
    try:
        with vector_path.open("r", encoding="utf-8") as handle:
            return list(deque(handle, maxlen=limit))
    except (OSError, UnicodeDecodeError):
        return []


def _tokens(text: str) -> list[str]:
    normalized: list[str] = []
    for token in _TOKEN_RE.findall(str(text or "")):
        lowered = token.lower()
        normalized.append(_KOREAN_PARTICLE_RE.sub("", lowered) or lowered)
    return normalized


def _keyword_terms(text: str) -> set[str]:
    tokens = _tokens(text)
    terms = set(tokens)
    for left, right in zip(tokens, tokens[1:]):
        if left and right:
            terms.add(f"{left}{right}")
    return terms


def _local_embedding(text: str) -> list[float]:
    values = [0.0] * _LOCAL_EMBEDDING_DIMENSIONS
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % _LOCAL_EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        values[idx] += sign
    norm = math.sqrt(sum(value * value for value in values))
    if not norm:
        return values
    return [value / norm for value in values]


def _voyage_embedding(text: str, *, input_type: str | None) -> tuple[list[float], str] | None:
    api_key = os.getenv("VOYAGE_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import httpx

        _provider, configured_model = _embedding_settings()
        model = configured_model or "voyage-4-large"
        payload: dict[str, Any] = {
            "input": text,
            "model": model,
            "truncation": True,
        }
        if input_type:
            payload["input_type"] = input_type
        dims = os.getenv("MIHO_DISCORD_EMBEDDING_DIMENSIONS", "").strip()
        if dims.isdigit() and int(dims) > 0:
            payload["output_dimension"] = int(dims)
        response = httpx.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        vector = data["data"][0]["embedding"]
    except Exception:
        return None
    return [float(value) for value in vector], model


def _openai_embedding(text: str) -> list[float] | None:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from openai import OpenAI

        kwargs: dict[str, Any] = {
            "api_key": api_key,
        }
        base_url = os.getenv("OPENAI_BASE_URL", "").strip()
        if base_url:
            kwargs["base_url"] = base_url
        client = OpenAI(**kwargs)
        provider, configured_model = _embedding_settings()
        model = configured_model if provider == "openai" else ""
        model = model or "text-embedding-3-small"
        request: dict[str, Any] = {"model": model, "input": text}
        dims = os.getenv("MIHO_DISCORD_EMBEDDING_DIMENSIONS", "").strip()
        if dims.isdigit() and int(dims) > 0:
            request["dimensions"] = int(dims)
        response = client.embeddings.create(**request)
        vector = response.data[0].embedding
    except Exception:
        return None
    return [float(value) for value in vector]


_LOCAL_MODEL_CACHE: dict[str, Any] = {}
_LOCAL_MODEL_DISABLED = False


def _local_model_enabled() -> bool:
    value = os.getenv("MIHO_LOCAL_EMBEDDING", "1").strip().lower()
    return value not in ("0", "false", "no", "off")


def _local_embedding_model_name() -> str:
    return os.getenv("MIHO_LOCAL_EMBEDDING_MODEL", "").strip() or "intfloat/multilingual-e5-large"


def _get_local_embedding_model() -> Any | None:
    """Lazily load the on-device embedding model (fastembed).

    Returns None when fastembed is unavailable or the model fails to load, so
    callers fall back to the non-semantic hash. The failure is cached so we
    don't retry a missing dependency on every call.
    """
    global _LOCAL_MODEL_DISABLED
    if _LOCAL_MODEL_DISABLED or not _local_model_enabled():
        return None
    name = _local_embedding_model_name()
    cached = _LOCAL_MODEL_CACHE.get(name)
    if cached is not None:
        return cached
    try:
        from fastembed import TextEmbedding

        model = TextEmbedding(name)
    except Exception:
        _LOCAL_MODEL_DISABLED = True
        return None
    _LOCAL_MODEL_CACHE[name] = model
    return model


def _local_model_embedding(text: str, *, input_type: str | None) -> tuple[list[float], str] | None:
    """On-device semantic embedding (no API key). Returns (vector, model_name) or None."""
    model = _get_local_embedding_model()
    if model is None:
        return None
    name = _local_embedding_model_name()
    # e5 models expect "query:"/"passage:" prefixes; other models take raw text.
    if "e5" in name.lower():
        prefix = "query: " if input_type == "query" else "passage: "
    else:
        prefix = ""
    try:
        vector = next(iter(model.embed([prefix + text])))
    except Exception:
        return None
    return [float(value) for value in vector], name


def embed_text(text: str, *, input_type: str | None = None) -> tuple[list[float], str]:
    """Return an embedding vector and the method used to create it.

    Order: Voyage -> OpenAI (API keys) -> on-device model (fastembed, no key)
    -> local-hash. Only the final hash is non-semantic; everything above is a
    real embedding so keyless installs still get semantic matching.
    """
    provider, configured_model = _embedding_settings()
    if provider in {"auto", "voyage"}:
        voyage_result = _voyage_embedding(text, input_type=input_type)
        if voyage_result:
            return voyage_result
    if provider in {"auto", "openai"}:
        vector = _openai_embedding(text)
        if vector:
            method = configured_model if provider == "openai" else ""
            return vector, method or "text-embedding-3-small"
    local_result = _local_model_embedding(text, input_type=input_type)
    if local_result:
        return local_result
    return _local_embedding(text), "local-hash-v1"


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _keyword_score(
    query: str,
    text: str,
    coverage_weight: float = _DEFAULT_RETRIEVAL_TUNING["keyword_coverage_weight"],
    precision_weight: float = _DEFAULT_RETRIEVAL_TUNING["keyword_precision_weight"],
) -> float:
    query_terms = _keyword_terms(query)
    text_terms = _keyword_terms(text)
    if not query_terms or not text_terms:
        return 0.0
    overlap = query_terms & text_terms
    if not overlap:
        return 0.0
    coverage = len(overlap) / len(query_terms)
    precision = len(overlap) / len(text_terms)
    return (coverage * coverage_weight) + (precision * precision_weight)


def _vector_record_text(record: dict[str, Any]) -> str:
    parts = [
        str(record.get("role") or ""),
        str(record.get("user_name") or ""),
        str(record.get("event_type") or ""),
        str(record.get("text") or ""),
    ]
    return "\n".join(part for part in parts if part)


def _dedupe_key(item: dict[str, Any]) -> str:
    role = str(item.get("role") or "")
    text = _SPACE_RE.sub("", str(item.get("text") or "")).strip().lower()
    return f"{role}:{text}"


def stored_embedding_method(rag_dir: Path) -> str:
    """Return the embedding method recorded in vector_index.json, or ''."""
    index_path = rag_dir / "vector_index.json"
    if not index_path.exists():
        return ""
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if isinstance(data, dict):
        return str(data.get("embedding_method") or "")
    return ""


def index_rag_record(rag_dir: Path, record: dict[str, Any]) -> dict[str, Any]:
    """Append a searchable vector record for one RAG message."""
    text = _vector_record_text(record)
    vector, method = embed_text(text, input_type="document")
    vector_path = rag_dir / "vectors.jsonl"
    vector_path.parent.mkdir(parents=True, exist_ok=True)
    # Detect an embedding-model switch: previously stored vectors live in a
    # different space and won't rank correctly until /memory rebuild. Warn once
    # at the transition (ignore hash-fallback flapping, which is transient).
    prior_method = stored_embedding_method(rag_dir)
    if (
        prior_method
        and prior_method != method
        and _HASH_METHOD not in (prior_method, method)
    ):
        logger.warning(
            "discord workspace embedding method changed (%s -> %s) in %s; "
            "existing vectors use the old embedding space and will rank poorly "
            "until '/memory rebuild' re-indexes them.",
            prior_method,
            method,
            rag_dir,
        )
    with path_lock(vector_path):
        count = count_lines(vector_path)
        payload = {
            "id": record.get("message_id") or f"memory-{count + 1}",
            "timestamp": record.get("timestamp") or "",
            "date": record.get("date") or "",
            "timezone": record.get("timezone") or "",
            "role": record.get("role") or "",
            "user_id": record.get("user_id") or "",
            "user_name": record.get("user_name") or "",
            "event_type": record.get("event_type") or "",
            "thread_id": record.get("thread_id") or "",
            "thread_name": record.get("thread_name") or "",
            "text": record.get("text") or "",
            "embedding_method": method,
            "embedding": vector,
        }
        with vector_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    metadata = {
        "version": 1,
        "embedding_method": method,
        "vector_count": count + 1,
        "vector_path": str(vector_path),
    }
    atomic_json_write(rag_dir / "vector_index.json", metadata, indent=2)
    return metadata


def retrieve_rag_context(
    rag_dir: Path,
    query: str,
    *,
    limit: int = 5,
    exclude_message_id: str | None = None,
    allowed_thread_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Return top hybrid vector/keyword matches for a query."""
    query = str(query or "").strip()
    vector_path = rag_dir / "vectors.jsonl"
    if not query or not vector_path.exists():
        return []
    query_vector, query_method = embed_text(query, input_type="query")
    query_is_hash = query_method == _HASH_METHOD
    if query_is_hash and str(rag_dir) not in _warned_hash_dirs:
        _warned_hash_dirs.add(str(rag_dir))
        logger.warning(
            "discord workspace RAG query embedding fell back to %s in %s; "
            "semantic ranking is disabled (keyword-only). Configure an embedding "
            "provider (Voyage/OpenAI) or the local model for semantic search.",
            _HASH_METHOD,
            rag_dir,
        )
    query_term_count = len(_keyword_terms(query))
    tuning = _retrieval_tuning()
    matches: list[dict[str, Any]] = []
    lines = _read_recent_vector_lines(vector_path, _max_scan_records())
    if not lines:
        return []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        if exclude_message_id and str(item.get("id") or "") == exclude_message_id:
            continue
        if allowed_thread_ids is not None and not _allowed_thread_item(item, allowed_thread_ids):
            continue
        vector = item.get("embedding")
        text = str(item.get("text") or "")
        if not isinstance(vector, list) or not text:
            continue
        method = str(item.get("embedding_method") or "")
        try:
            stored_vector = [float(value) for value in vector]
        except (TypeError, ValueError):
            continue
        # Hash-fallback embeddings carry no semantic meaning, so their cosine is
        # noise. Trust semantic only when neither side is hash-fallback and the
        # dimensions match; otherwise fall back to keyword-only ranking.
        usable_semantic = (
            not query_is_hash
            and method != _HASH_METHOD
            and len(query_vector) == len(stored_vector)
        )
        semantic = (
            max(0.0, _cosine_similarity(query_vector, stored_vector))
            if usable_semantic
            else 0.0
        )
        keyword = _keyword_score(
            query,
            text,
            tuning["keyword_coverage_weight"],
            tuning["keyword_precision_weight"],
        )
        if keyword == 0 and method == _HASH_METHOD:
            continue
        if keyword == 0 and semantic < tuning["min_semantic_no_keyword"]:
            continue
        if keyword < tuning["min_keyword"] and semantic < tuning["min_semantic"]:
            continue
        if (
            query_term_count >= tuning["long_query_terms"]
            and keyword < tuning["long_query_min_keyword"]
            and semantic < tuning["long_query_min_semantic"]
        ):
            continue
        score = (semantic * tuning["semantic_weight"]) + (keyword * tuning["keyword_weight"])
        if score <= 0:
            continue
        matches.append({
            **item,
            "score": min(score, 1.0),
            "semantic_score": semantic,
            "keyword_score": keyword,
        })
    matches.sort(key=lambda item: item.get("score", 0.0), reverse=True)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in matches:
        key = _dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
        if len(deduped) >= limit:
            break
    return deduped


def _allowed_thread_item(item: dict[str, Any], allowed_thread_ids: set[str]) -> bool:
    thread_id = str(item.get("thread_id") or "")
    event_type = str(item.get("event_type") or "")
    if thread_id:
        return thread_id in allowed_thread_ids
    return event_type != "thread_message"
