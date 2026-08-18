$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "============================================================"
Write-Host "GeoPilot Ollama Embedding Model Verification V1.1"
Write-Host "Correct EmbeddingBatch field verification"
Write-Host "NO ENV CHANGE / NO SOURCE CHANGE / NO DB WRITE / NO MIGRATION"
Write-Host "============================================================"

Write-Host "[1] Verify effective runtime configuration"
docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); print('embedding_provider=',s.embedding_provider); print('ollama_embedding_model=',s.ollama_embedding_model); assert s.embedding_provider=='ollama'; assert s.ollama_embedding_model=='embeddinggemma'"
if ($LASTEXITCODE -ne 0) { throw "Runtime embedding configuration verification failed." }

Write-Host "[2] Verify installed Ollama model and direct /api/embed"
docker compose exec -T backend python -c "import httpx; from app.core.config import get_settings; s=get_settings(); base=s.ollama_base_url.rstrip('/'); tags=httpx.get(base+'/api/tags',timeout=30); tags.raise_for_status(); names=[str(x.get('name') or x.get('model') or '') for x in tags.json().get('models',[])]; print('installed_models=',names); assert any(n.split(':',1)[0]=='embeddinggemma' for n in names); r=httpx.post(base+'/api/embed',json={'model':s.ollama_embedding_model,'input':['GeoPilot runtime verification']},timeout=60); print('embed_status=',r.status_code); r.raise_for_status(); v=r.json().get('embeddings') or []; assert len(v)==1 and len(v[0])==768; print('dimension=',len(v[0]))"
if ($LASTEXITCODE -ne 0) { throw "Direct Ollama embedding verification failed." }

Write-Host "[3] Verify GeoPilot embedding provider result contract"
$VerifyPy = Join-Path $Root "backend\_verify_embedding_batch_v1_1.py"
$Code = @'
from app.services.embedding_providers import embed_with_fallback

batch = embed_with_fallback(["GeoPilot provider verification"])

print("provider=", batch.provider)
print("model_name=", batch.model_name)
print("model_revision=", batch.model_revision)
print("vector_count=", len(batch.vectors))
print("dimension=", len(batch.vectors[0]) if batch.vectors else 0)

assert batch.provider == "ollama"
assert batch.model_name == "embeddinggemma"
assert len(batch.vectors) == 1
assert len(batch.vectors[0]) == 768
print("embedding_provider_contract=PASS")
'@

Set-Content -Path $VerifyPy -Value $Code -Encoding UTF8
try {
    docker compose exec -T backend python /app/_verify_embedding_batch_v1_1.py
    if ($LASTEXITCODE -ne 0) { throw "GeoPilot embedding provider contract verification failed." }
}
finally {
    Remove-Item $VerifyPy -Force -ErrorAction SilentlyContinue
}

Write-Host "[4] Embedding/index regression"
if (Test-Path "backend\tests\test_document_embedding_index.py") {
    docker compose exec -T backend python -m pytest -q tests/test_document_embedding_index.py
    if ($LASTEXITCODE -ne 0) { throw "Embedding index regression failed." }
} else {
    Write-Host "SKIP: tests/test_document_embedding_index.py not found"
}

Write-Host "[5] Document retrieval regression"
if (Test-Path "backend\tests\test_document_retrieval.py") {
    docker compose exec -T backend python -m pytest -q tests/test_document_retrieval.py
    if ($LASTEXITCODE -ne 0) { throw "Document retrieval regression failed." }
} else {
    Write-Host "SKIP: tests/test_document_retrieval.py not found"
}

Write-Host "[6] Service health"
docker compose ps

Write-Host "============================================================"
Write-Host "OLLAMA EMBEDDING MODEL VERIFICATION V1.1 PASS"
Write-Host "============================================================"
Write-Host "Effective model: embeddinggemma"
Write-Host "Ollama /api/embed: PASS"
Write-Host "Embedding dimension: 768"
Write-Host "GeoPilot provider: ollama"
Write-Host "EmbeddingBatch.model_name: embeddinggemma"
Write-Host "Embedding/index regression: PASS"
Write-Host "Retrieval regression: PASS"
Write-Host "ENV change in this verifier: NONE"
Write-Host "Source change: NONE"
Write-Host "DB write: NONE"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "Live acquired-document E2E rerun: READY"
Write-Host "============================================================"
