# TASK-020 — Embedding / Index Pipeline

Status: IMPLEMENTED / EXECUTABLE UNIT ACCEPTANCE TARGET

## Scope
- Server-owned embedding provider registry: Ollama primary, OpenAI fallback/configurable.
- No API key, base URL, or arbitrary provider endpoint is accepted from clients.
- Persist exact embedding provider/model/revision/dimensions provenance.
- Persist chunk vectors in native PostgreSQL `vector` columns.
- Version index state becomes `ready` only after every current chunk has a validated vector.
- Provider failure or malformed/inconsistent vectors fail closed.
- Stable UUIDv5 identities for an unchanged version/provider/model/dimension index and its chunk embeddings.

## Explicitly deferred
- Keyword/vector hybrid ranking, similarity query APIs, HNSW/IVFFlat tuning: TASK-021.
- Citation presentation/ranking: TASK-022.
- Planning Officer retrieval orchestration: later tasks.
