from __future__ import annotations

import pytest

from app.core.config import Settings
from app.services.embedding_providers import (
    EmbeddingBatch,
    EmbeddingProviderError,
    _validate_vectors,
    embed_with_fallback,
)


def test_vector_validation_rejects_count_dimension_and_nonfinite():
    assert _validate_vectors([[1, 2], [3, 4]], expected_count=2) == [[1.0, 2.0], [3.0, 4.0]]
    with pytest.raises(EmbeddingProviderError):
        _validate_vectors([[1, 2]], expected_count=2)
    with pytest.raises(EmbeddingProviderError):
        _validate_vectors([[1, 2], [3]], expected_count=2)
    with pytest.raises(EmbeddingProviderError):
        _validate_vectors([[1, float("nan")]], expected_count=1)


def test_fallback_retries_whole_request_on_primary_failure(monkeypatch):
    settings = Settings(
        EMBEDDING_PROVIDER="ollama",
        EMBEDDING_FALLBACK_PROVIDER="openai",
        OPENAI_API_KEY="x",
        OPENAI_EMBEDDING_MODEL="embed-test",
    )
    calls=[]
    class Provider:
        def __init__(self, name): self.name=name
        def embed(self, texts):
            calls.append((self.name, list(texts)))
            if self.name == "ollama": raise EmbeddingProviderError("primary down")
            return EmbeddingBatch("openai", "embed-test", "provider_managed", [[0.1,0.2] for _ in texts])
    monkeypatch.setattr("app.services.embedding_providers.build_provider", lambda name, settings=None: Provider(name))
    result=embed_with_fallback(["a","b"], settings)
    assert result.provider == "openai"
    assert calls == [("ollama", ["a","b"]), ("openai", ["a","b"])]


def test_fallback_failure_is_fail_closed(monkeypatch):
    settings = Settings(EMBEDDING_PROVIDER="ollama", EMBEDDING_FALLBACK_PROVIDER="openai")
    class Provider:
        def embed(self, texts): raise EmbeddingProviderError("down")
    monkeypatch.setattr("app.services.embedding_providers.build_provider", lambda name, settings=None: Provider())
    with pytest.raises(EmbeddingProviderError, match="all configured embedding providers failed"):
        embed_with_fallback(["a"], settings)
