import json
import sys
from types import ModuleType, SimpleNamespace

from gateway.discord_workspace_vectors import embed_text, retrieve_rag_context


def test_embed_text_uses_local_fallback_without_openai_key(monkeypatch):
    # 키가 없고 on-device 모델(fastembed)도 꺼졌을 때만 비의미적 해시로 떨어진다.
    # 로컬 모델이 설치/활성이면 그게 우선이므로(e5-large) 해시 폴백을 보려면 끈다.
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setenv("MIHO_LOCAL_EMBEDDING", "0")

    vector, method = embed_text("Miho local fallback")

    assert method == "local-hash-v1"
    assert len(vector) == 256


def test_embed_text_uses_openai_when_key_is_configured(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "test-key"
            self.embeddings = SimpleNamespace(create=self._create)

        def _create(self, **kwargs):
            assert kwargs["model"] == "text-embedding-3-small"
            assert kwargs["input"] == "Miho semantic memory"
            return SimpleNamespace(
                data=[
                    SimpleNamespace(
                        embedding=[0.1, 0.2, 0.3],
                    )
                ]
            )

    fake_module = ModuleType("openai")
    fake_module.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("MIHO_DISCORD_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("MIHO_DISCORD_EMBEDDING_MODEL", raising=False)

    vector, method = embed_text("Miho semantic memory")

    assert method == "text-embedding-3-small"
    assert vector == [0.1, 0.2, 0.3]


def test_embed_text_prefers_voyage_when_key_is_configured(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"embedding": [0.4, 0.5, 0.6]}]}

    def fake_post(url, *, headers, json, timeout):
        assert url == "https://api.voyageai.com/v1/embeddings"
        assert headers["Authorization"] == "Bearer voyage-key"
        assert json["model"] == "voyage-4-large"
        assert json["input_type"] == "query"
        assert timeout == 10.0
        return FakeResponse()

    fake_module = ModuleType("httpx")
    fake_module.post = fake_post
    monkeypatch.setitem(sys.modules, "httpx", fake_module)
    monkeypatch.setenv("VOYAGE_API_KEY", "voyage-key")
    monkeypatch.delenv("MIHO_DISCORD_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("MIHO_DISCORD_EMBEDDING_MODEL", raising=False)

    vector, method = embed_text("Miho semantic memory", input_type="query")

    assert method == "voyage-4-large"
    assert vector == [0.4, 0.5, 0.6]


def test_voyage_api_key_is_available_in_miho_settings():
    from miho_cli.config import OPTIONAL_ENV_VARS

    info = OPTIONAL_ENV_VARS["VOYAGE_API_KEY"]
    assert info["password"] is True
    assert info["category"] == "tool"
    assert "discord_workspace_rag" in info["tools"]


def test_retrieve_rag_context_uses_cosine_for_external_vectors(monkeypatch, tmp_path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    vector_path = rag_dir / "vectors.jsonl"
    vector_path.write_text(
        json.dumps({
            "id": "m1",
            "role": "user",
            "user_name": "Max",
            "text": "PACA Peak 로그인 연동 기준",
            "embedding_method": "voyage-4-large",
            "embedding": [100.0, 0.0],
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "gateway.discord_workspace_vectors.embed_text",
        lambda text, input_type=None: ([10.0, 0.0], "voyage-4-large"),
    )

    matches = retrieve_rag_context(rag_dir, "PACA 로그인", limit=1)

    assert matches
    assert 0 < matches[0]["score"] <= 1.0
    assert matches[0]["semantic_score"] == 1.0


def test_retrieve_rag_context_matches_compacted_korean_keyword(monkeypatch, tmp_path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    vector_path = rag_dir / "vectors.jsonl"
    rows = [
        {
            "id": "m1",
            "role": "user",
            "user_name": "Max",
            "text": "학생 카드 디자인을 HTML 이미지로 만든다.",
            "embedding_method": "voyage-4-large",
            "embedding": [0.0, 1.0],
        },
        {
            "id": "m2",
            "role": "user",
            "user_name": "Max",
            "text": "점심 메뉴를 정한다.",
            "embedding_method": "voyage-4-large",
            "embedding": [0.0, 1.0],
        },
    ]
    vector_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "gateway.discord_workspace_vectors.embed_text",
        lambda text, input_type=None: ([1.0, 0.0], "voyage-4-large"),
    )

    matches = retrieve_rag_context(rag_dir, "학생카드", limit=2)

    assert [item["id"] for item in matches] == ["m1"]
    assert matches[0]["keyword_score"] > 0.6


def test_retrieve_rag_context_ignores_semantic_when_vector_dimensions_differ(
    monkeypatch,
    tmp_path,
):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    vector_path = rag_dir / "vectors.jsonl"
    vector_path.write_text(
        json.dumps({
            "id": "m1",
            "role": "user",
            "user_name": "Max",
            "text": "학생카드 기준",
            "embedding_method": "voyage-4-large",
            "embedding": [1.0, 0.0, 0.0],
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "gateway.discord_workspace_vectors.embed_text",
        lambda text, input_type=None: ([1.0, 0.0], "local-hash-v1"),
    )

    matches = retrieve_rag_context(rag_dir, "학생카드", limit=1)

    assert matches
    assert matches[0]["semantic_score"] == 0.0
    assert matches[0]["keyword_score"] > 0.0


def test_retrieve_rag_context_deduplicates_repeated_text(monkeypatch, tmp_path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    vector_path = rag_dir / "vectors.jsonl"
    rows = [
        {
            "id": "m1",
            "role": "user",
            "text": "박지안 학생카드 줘",
            "embedding_method": "voyage-4-large",
            "embedding": [1.0, 0.0],
        },
        {
            "id": "m2",
            "role": "user",
            "text": "박지안 학생카드줘",
            "embedding_method": "voyage-4-large",
            "embedding": [1.0, 0.0],
        },
    ]
    vector_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "gateway.discord_workspace_vectors.embed_text",
        lambda text, input_type=None: ([1.0, 0.0], "voyage-4-large"),
    )

    matches = retrieve_rag_context(rag_dir, "박지안 학생카드", limit=5)

    assert [item["id"] for item in matches] == ["m1"]


def test_retrieve_rag_context_filters_weak_partial_matches(monkeypatch, tmp_path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    vector_path = rag_dir / "vectors.jsonl"
    rows = [
        {
            "id": "m1",
            "role": "user",
            "text": "박지안 학생카드 줘",
            "embedding_method": "voyage-4-large",
            "embedding": [0.0, 1.0],
        },
        {
            "id": "m2",
            "role": "user",
            "text": "김동하 학생카드 줘",
            "embedding_method": "voyage-4-large",
            "embedding": [0.0, 1.0],
        },
    ]
    vector_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "gateway.discord_workspace_vectors.embed_text",
        lambda text, input_type=None: ([1.0, 0.0], "voyage-4-large"),
    )

    matches = retrieve_rag_context(rag_dir, "박지안 학생카드", limit=5)

    assert [item["id"] for item in matches] == ["m1"]


def test_retrieve_rag_context_scans_recent_records_only(monkeypatch, tmp_path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    vector_path = rag_dir / "vectors.jsonl"
    rows = [
        {
            "id": f"m{idx}",
            "role": "user",
            "text": f"학생카드 기록 {idx}",
            "embedding_method": "voyage-4-large",
            "embedding": [1.0, 0.0],
        }
        for idx in range(4)
    ]
    vector_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MIHO_DISCORD_RAG_MAX_SCAN_RECORDS", "2")
    monkeypatch.setattr(
        "gateway.discord_workspace_vectors.embed_text",
        lambda text, input_type=None: ([1.0, 0.0], "voyage-4-large"),
    )

    matches = retrieve_rag_context(rag_dir, "학생카드", limit=4)

    assert [item["id"] for item in matches] == ["m2", "m3"]


def test_retrieve_rag_context_skips_corrupt_embedding_rows(monkeypatch, tmp_path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    vector_path = rag_dir / "vectors.jsonl"
    rows = [
        {
            "id": "bad",
            "role": "user",
            "text": "학생카드 손상 데이터",
            "embedding_method": "voyage-4-large",
            "embedding": ["not-a-number"],
        },
        {
            "id": "good",
            "role": "user",
            "text": "학생카드 정상 데이터",
            "embedding_method": "voyage-4-large",
            "embedding": [1.0, 0.0],
        },
    ]
    vector_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "gateway.discord_workspace_vectors.embed_text",
        lambda text, input_type=None: ([1.0, 0.0], "voyage-4-large"),
    )

    matches = retrieve_rag_context(rag_dir, "학생카드", limit=5)

    assert [item["id"] for item in matches] == ["good"]


def test_embed_text_uses_local_model_when_no_api_keys(monkeypatch):
    """No Voyage/OpenAI key → on-device model used (semantic method, not hash)."""
    import gateway.discord_workspace_vectors as v

    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MIHO_DISCORD_EMBEDDING_PROVIDER", "auto")
    seen = {}

    class FakeModel:
        def embed(self, texts):
            seen["texts"] = list(texts)
            for _ in texts:
                yield [0.1, 0.2, 0.3]

    monkeypatch.setattr(v, "_get_local_embedding_model", lambda: FakeModel())
    monkeypatch.setattr(v, "_local_embedding_model_name", lambda: "intfloat/multilingual-e5-large")

    vector, method = v.embed_text("로그인", input_type="query")
    assert method == "intfloat/multilingual-e5-large"
    assert vector == [0.1, 0.2, 0.3]
    assert seen["texts"] == ["query: 로그인"]  # e5 query prefix applied


def test_local_model_uses_passage_prefix_for_documents(monkeypatch):
    import gateway.discord_workspace_vectors as v

    seen = {}

    class FakeModel:
        def embed(self, texts):
            seen["texts"] = list(texts)
            for _ in texts:
                yield [1.0]

    monkeypatch.setattr(v, "_get_local_embedding_model", lambda: FakeModel())
    monkeypatch.setattr(v, "_local_embedding_model_name", lambda: "intfloat/multilingual-e5-large")

    v._local_model_embedding("학생 카드", input_type="document")
    assert seen["texts"] == ["passage: 학생 카드"]


def test_embed_text_falls_back_to_hash_without_local_model(monkeypatch):
    """No keys and no fastembed → non-semantic local-hash (graceful)."""
    import gateway.discord_workspace_vectors as v

    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("MIHO_DISCORD_EMBEDDING_PROVIDER", "auto")
    monkeypatch.setattr(v, "_get_local_embedding_model", lambda: None)

    _vector, method = v.embed_text("로그인", input_type="query")
    assert method == "local-hash-v1"


def test_local_model_disabled_by_env(monkeypatch):
    import gateway.discord_workspace_vectors as v

    monkeypatch.setenv("MIHO_LOCAL_EMBEDDING", "0")
    v._LOCAL_MODEL_CACHE.clear()
    monkeypatch.setattr(v, "_LOCAL_MODEL_DISABLED", False)
    assert v._get_local_embedding_model() is None
