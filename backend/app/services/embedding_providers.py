from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings


class EmbeddingProviderError(Exception):
    pass


@dataclass(frozen=True)
class EmbeddingBatch:
    provider: str
    model_name: str
    model_revision: str
    vectors: list[list[float]]


class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    model_revision: str

    def embed(self, texts: list[str]) -> EmbeddingBatch: ...


def _validate_vectors(vectors: object, *, expected_count: int) -> list[list[float]]:
    if not isinstance(vectors, list) or len(vectors) != expected_count:
        raise EmbeddingProviderError("embedding provider returned an unexpected vector count")
    clean: list[list[float]] = []
    dimensions: int | None = None
    for vector in vectors:
        if not isinstance(vector, list) or not vector:
            raise EmbeddingProviderError("embedding provider returned an empty or malformed vector")
        try:
            values = [float(item) for item in vector]
        except (TypeError, ValueError) as exc:
            raise EmbeddingProviderError("embedding provider returned non-numeric vector values") from exc
        if any(value != value or value in (float("inf"), float("-inf")) for value in values):
            raise EmbeddingProviderError("embedding provider returned non-finite vector values")
        dimensions = dimensions or len(values)
        if len(values) != dimensions:
            raise EmbeddingProviderError("embedding provider returned inconsistent vector dimensions")
        if dimensions > 4096:
            raise EmbeddingProviderError("embedding dimensions exceed GeoPilot v1 limit")
        clean.append(values)
    return clean


class OllamaEmbeddingProvider:
    provider_name = "ollama"
    model_revision = "server_resolved"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.ollama_embedding_model.strip()
        if not self.model_name:
            raise EmbeddingProviderError("OLLAMA_EMBEDDING_MODEL is required")

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        vectors: list[list[float]] = []
        url = self.settings.ollama_base_url.rstrip("/") + "/api/embed"
        try:
            with httpx.Client(timeout=self.settings.embedding_timeout_seconds) as client:
                for start in range(0, len(texts), self.settings.embedding_batch_size):
                    batch = texts[start:start + self.settings.embedding_batch_size]
                    response = client.post(url, json={"model": self.model_name, "input": batch})
                    response.raise_for_status()
                    payload = response.json()
                    vectors.extend(_validate_vectors(payload.get("embeddings"), expected_count=len(batch)))
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise EmbeddingProviderError(f"Ollama embedding request failed: {exc}") from exc
        return EmbeddingBatch(self.provider_name, self.model_name, self.model_revision, vectors)


class OpenAIEmbeddingProvider:
    provider_name = "openai"
    model_revision = "provider_managed"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = (settings.openai_embedding_model or "").strip()
        if not settings.openai_api_key:
            raise EmbeddingProviderError("OPENAI_API_KEY is required for OpenAI embeddings")
        if not self.model_name:
            raise EmbeddingProviderError("OPENAI_EMBEDDING_MODEL is required")

    def embed(self, texts: list[str]) -> EmbeddingBatch:
        vectors: list[list[float]] = []
        url = self.settings.openai_base_url.rstrip("/") + "/embeddings"
        headers = {"Authorization": f"Bearer {self.settings.openai_api_key}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self.settings.embedding_timeout_seconds) as client:
                for start in range(0, len(texts), self.settings.embedding_batch_size):
                    batch = texts[start:start + self.settings.embedding_batch_size]
                    response = client.post(url, headers=headers, json={"model": self.model_name, "input": batch})
                    response.raise_for_status()
                    data = response.json().get("data")
                    if not isinstance(data, list) or len(data) != len(batch):
                        raise EmbeddingProviderError("OpenAI returned an unexpected embedding count")
                    ordered = sorted(data, key=lambda item: item.get("index", -1))
                    raw = [item.get("embedding") for item in ordered]
                    vectors.extend(_validate_vectors(raw, expected_count=len(batch)))
        except EmbeddingProviderError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise EmbeddingProviderError(f"OpenAI embedding request failed: {exc}") from exc
        return EmbeddingBatch(self.provider_name, self.model_name, self.model_revision, vectors)


def build_provider(name: str, settings: Settings | None = None) -> EmbeddingProvider:
    settings = settings or get_settings()
    if name == "ollama":
        return OllamaEmbeddingProvider(settings)
    if name == "openai":
        return OpenAIEmbeddingProvider(settings)
    raise EmbeddingProviderError("embedding provider is not registered")


def embed_with_fallback(texts: list[str], settings: Settings | None = None) -> EmbeddingBatch:
    settings = settings or get_settings()
    attempted: list[str] = []
    errors: list[str] = []
    for provider_name in [settings.embedding_provider, settings.embedding_fallback_provider]:
        if not provider_name or provider_name in attempted:
            continue
        attempted.append(provider_name)
        try:
            return build_provider(provider_name, settings).embed(texts)
        except EmbeddingProviderError as exc:
            errors.append(f"{provider_name}: {exc}")
    raise EmbeddingProviderError("all configured embedding providers failed: " + "; ".join(errors))
