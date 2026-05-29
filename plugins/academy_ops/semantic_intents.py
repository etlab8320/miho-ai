"""Embedding-based intent classification for academy fast-path routing.

Replaces hardcoded keyword dictionaries with semantic matching against a small
set of example utterances per intent. Reuses the existing embedding stack
(:func:`gateway.discord_workspace_vectors.embed_text`) so the embedding model is
never hardcoded — it follows ``MIHO_DISCORD_EMBEDDING_*`` configuration
(Voyage / OpenAI / local-hash fallback).

Safety contract: the local-hash fallback is *not* semantic, so whenever a real
embedding provider is unavailable (or routing is disabled / the match is
ambiguous) :func:`classify` returns ``None`` to signal "abstain" — callers then
fall back to their existing keyword logic, preserving prior behaviour exactly.
"""

from __future__ import annotations

import math
import os

# Cache of anchor vectors per intent group (process lifetime).
# Only successful (semantic) results are cached; non-semantic / error results
# are never stored so a transient provider outage cannot become a permanent
# downgrade in a long-lived gateway process.
_anchor_cache: dict[str, list[tuple[str, list[float]]]] = {}


def semantic_routing_enabled() -> bool:
    """Whether embedding-based routing is active (default on; flag to roll back)."""
    value = os.getenv("MIHO_ACADEMY_SEMANTIC_ROUTING", "1").strip().lower()
    return value not in ("0", "false", "no", "off")


def _threshold(default: float = 0.5) -> float:
    raw = os.getenv("MIHO_ACADEMY_SEMANTIC_THRESHOLD", "").strip()
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if 0.0 < value <= 1.0 else default


def _is_semantic(method: str) -> bool:
    """True when *method* is a real embedding (not the local-hash fallback).

    ``embed_text`` returns ``"local-hash-v1"`` only when no semantic provider is
    available; every real provider (Voyage, OpenAI, future ones) returns its
    model name. Matching the single non-semantic sentinel keeps this provider-
    agnostic — no provider allowlist to keep in sync.
    """
    method = str(method or "")
    return bool(method) and not method.startswith("local-hash")


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if not norm_a or not norm_b:
        return 0.0
    return dot / (norm_a * norm_b)


def _embed(text: str, input_type: str) -> tuple[list[float], str]:
    from gateway.discord_workspace_vectors import embed_text

    return embed_text(text, input_type=input_type)


def _anchor_vectors(group_key: str, intents: dict[str, tuple[str, ...]]) -> list[tuple[str, list[float]]]:
    cached = _anchor_cache.get(group_key)
    if cached:  # only non-empty (successful) results are ever cached
        return cached
    vectors: list[tuple[str, list[float]]] = []
    for intent, examples in intents.items():
        for example in examples:
            try:
                vector, method = _embed(example, "document")
            except Exception:
                return []  # not cached → retried next call (provider may recover)
            if not _is_semantic(method):
                return []  # anchors fell back to local-hash → abstain, not cached
            vectors.append((intent, vector))
    _anchor_cache[group_key] = vectors
    return vectors


def classify(
    text: str,
    group_key: str,
    intents: dict[str, tuple[str, ...]],
    *,
    threshold: float | None = None,
) -> str | None:
    """Return the best-matching intent label, or ``None`` to abstain.

    Abstains (returns ``None``, caller should use keyword fallback) when:
      * semantic routing is disabled,
      * the embedding provider is the non-semantic local-hash fallback,
      * the top similarity is below the confidence threshold (ambiguous).

    When a real embedding provider is available and the match is confident, the
    best label is returned — including a designated negative label (e.g.
    ``"none"``) so callers can treat a confident "not this intent" as a decision
    rather than falling back to keywords.
    """
    if not semantic_routing_enabled():
        return None
    text = (text or "").strip()
    if not text:
        return None
    try:
        query_vector, query_method = _embed(text, "query")
    except Exception:
        return None
    if not _is_semantic(query_method):
        return None
    anchors = _anchor_vectors(group_key, intents)
    if not anchors:
        return None
    best_label: str | None = None
    best_score = -1.0
    for label, anchor_vector in anchors:
        score = _cosine(query_vector, anchor_vector)
        if score > best_score:
            best_score = score
            best_label = label
    if best_score < (threshold if threshold is not None else _threshold()):
        return None
    return best_label
