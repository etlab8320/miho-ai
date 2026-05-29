"""Hash-fallback safety and embedding-model-switch detection.

A hash-fallback embedding (local-hash-v1) carries no semantic meaning, so its
cosine similarity is noise. Retrieval must drop the semantic signal (keyword
only) when either the query or a stored vector is hash-fallback, warn once on a
keyless query, and warn when the embedding model changes under existing vectors.
"""

from __future__ import annotations

import logging

import gateway.discord_workspace_vectors as v


def _fake_embed(method: str):
    def _embed(text: str, input_type: str = "document"):
        return [1.0, 0.0], method

    return _embed


def _record(mid: str, text: str) -> dict[str, object]:
    return {"message_id": mid, "text": text, "role": "user", "user_name": "u"}


def test_stored_embedding_method(tmp_path, monkeypatch) -> None:
    assert v.stored_embedding_method(tmp_path) == ""
    monkeypatch.setattr(v, "embed_text", _fake_embed("voyage-4-large"))
    v.index_rag_record(tmp_path, _record("m1", "hello world"))
    assert v.stored_embedding_method(tmp_path) == "voyage-4-large"


def test_hash_query_disables_semantic_but_keeps_keyword(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(v, "embed_text", _fake_embed("voyage-4-large"))
    v.index_rag_record(tmp_path, _record("m1", "제자리 멀리뛰기 기록"))
    # Query embedding falls back to hash -> semantic must be ignored.
    v._warned_hash_dirs.clear()
    monkeypatch.setattr(v, "embed_text", _fake_embed("local-hash-v1"))
    results = v.retrieve_rag_context(tmp_path, "제자리 멀리뛰기")
    assert results, "keyword match should still surface the record"
    assert all(r["semantic_score"] == 0.0 for r in results)


def test_stored_hash_vector_ignored_for_semantic(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(v, "embed_text", _fake_embed("local-hash-v1"))
    v.index_rag_record(tmp_path, _record("m1", "제자리 멀리뛰기 기록"))
    # Real query, but the stored vector is hash-fallback -> semantic ignored.
    monkeypatch.setattr(v, "embed_text", _fake_embed("voyage-4-large"))
    results = v.retrieve_rag_context(tmp_path, "제자리 멀리뛰기")
    assert all(r["semantic_score"] == 0.0 for r in results)


def test_hash_query_warns_once(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setattr(v, "embed_text", _fake_embed("local-hash-v1"))
    v.index_rag_record(tmp_path, _record("m1", "hello"))
    v._warned_hash_dirs.clear()
    with caplog.at_level(logging.WARNING):
        v.retrieve_rag_context(tmp_path, "hello")
        v.retrieve_rag_context(tmp_path, "hello")
    hits = [r for r in caplog.records if "fell back" in r.getMessage()]
    assert len(hits) == 1, "should warn exactly once per dir per process"


def test_model_switch_warns(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setattr(v, "embed_text", _fake_embed("voyage-4-large"))
    v.index_rag_record(tmp_path, _record("m1", "hello"))
    monkeypatch.setattr(v, "embed_text", _fake_embed("openai-3-small"))
    with caplog.at_level(logging.WARNING):
        v.index_rag_record(tmp_path, _record("m2", "world"))
    assert any("embedding method changed" in r.getMessage() for r in caplog.records)


def test_hash_flap_does_not_warn_as_switch(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setattr(v, "embed_text", _fake_embed("voyage-4-large"))
    v.index_rag_record(tmp_path, _record("m1", "hello"))
    monkeypatch.setattr(v, "embed_text", _fake_embed("local-hash-v1"))
    with caplog.at_level(logging.WARNING):
        v.index_rag_record(tmp_path, _record("m2", "world"))
    assert not any("embedding method changed" in r.getMessage() for r in caplog.records)
