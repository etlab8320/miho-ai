import sys
from types import ModuleType, SimpleNamespace

from gateway.discord_workspace_vectors import embed_text


def test_embed_text_uses_local_fallback_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

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
