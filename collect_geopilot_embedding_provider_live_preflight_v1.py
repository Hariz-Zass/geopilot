from __future__ import annotations

import sys
import httpx
from app.core.config import get_settings

print("=" * 72)
print("GEOPILOT EMBEDDING PROVIDER LIVE PREFLIGHT V1")
print("READ ONLY - NO CONFIG CHANGE")
print("=" * 72)

settings = get_settings()
base = settings.ollama_base_url.rstrip("/")
configured = settings.ollama_embedding_model

print("[1] Effective GeoPilot embedding configuration")
print("embedding_provider:", settings.embedding_provider)
print("embedding_fallback_provider:", settings.embedding_fallback_provider)
print("ollama_base_url:", base)
print("ollama_embedding_model:", configured)
print("openai_embedding_model_configured:", bool(settings.openai_embedding_model))
print("openai_api_key_configured:", bool(settings.openai_api_key))

print()
print("[2] Ollama tags/model discovery")
try:
    with httpx.Client(timeout=20.0) as client:
        response = client.get(base + "/api/tags")
        print("tags_status:", response.status_code)
        response.raise_for_status()
        payload = response.json()
except Exception as exc:
    print("OLLAMA_TAGS_FAILED:", type(exc).__name__, str(exc))
    sys.exit(2)

models = []
for item in payload.get("models", []):
    name = str(item.get("name") or item.get("model") or "").strip()
    if name:
        models.append(name)

for name in models:
    print("model:", name)

def model_present(requested: str) -> bool:
    wanted = requested.casefold()
    aliases = {wanted, wanted + ":latest"} if ":" not in wanted else {wanted}
    return any(name.casefold() in aliases for name in models)

print("configured_model_present:", model_present(configured))

print()
print("[3] Direct /api/embed test using configured model")
configured_ok = False
try:
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            base + "/api/embed",
            json={"model": configured, "input": ["GeoPilot embedding preflight"]},
        )
        print("configured_embed_status:", r.status_code)
        if r.is_success:
            data = r.json()
            vectors = data.get("embeddings") or []
            dim = len(vectors[0]) if vectors and isinstance(vectors[0], list) else 0
            print("configured_embed_vector_count:", len(vectors))
            print("configured_embed_dimension:", dim)
            configured_ok = bool(vectors and dim > 0)
        else:
            print("configured_embed_error_preview:", r.text[:500])
except Exception as exc:
    print("configured_embed_exception:", type(exc).__name__, str(exc))

print()
print("[4] Candidate installed embedding-model tests")
candidates = []
for preferred in ("embeddinggemma", "nomic-embed-text"):
    if model_present(preferred):
        candidates.append(preferred)

for name in models:
    low = name.casefold()
    if any(token in low for token in ("embed", "embedding", "bge", "e5")):
        base_name = name.split(":", 1)[0]
        if base_name not in candidates:
            candidates.append(base_name)

candidate_successes = []
for candidate in candidates:
    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                base + "/api/embed",
                json={"model": candidate, "input": ["GeoPilot embedding candidate test"]},
            )
        print(f"candidate={candidate} status={r.status_code}")
        if r.is_success:
            data = r.json()
            vectors = data.get("embeddings") or []
            dim = len(vectors[0]) if vectors and isinstance(vectors[0], list) else 0
            print(f"candidate={candidate} dimension={dim}")
            if vectors and dim > 0:
                candidate_successes.append((candidate, dim))
        else:
            print(f"candidate={candidate} error_preview={r.text[:300]}")
    except Exception as exc:
        print(f"candidate={candidate} exception={type(exc).__name__}: {exc}")

print()
print("[5] Diagnosis")
if configured_ok:
    print("DIAGNOSIS=CONFIGURED_OLLAMA_EMBEDDING_WORKS")
    print("ACTION=NO_MODEL_CHANGE_REQUIRED")
    sys.exit(0)

if candidate_successes:
    print("DIAGNOSIS=CONFIGURED_MODEL_FAILED_BUT_INSTALLED_MODEL_WORKS")
    for model, dim in candidate_successes:
        print(f"WORKING_MODEL={model}")
        print(f"WORKING_DIMENSION={dim}")
    print("ACTION=UPDATE_OLLAMA_EMBEDDING_MODEL_TO_A_WORKING_MODEL_AND_RESTART_BACKEND")
    sys.exit(0)

print("DIAGNOSIS=NO_TESTED_OLLAMA_EMBEDDING_MODEL_WORKS")
print("ACTION=DO_NOT_CHANGE_CONFIG_YET; INSPECT OLLAMA VERSION/API/MODELS")
sys.exit(3)
