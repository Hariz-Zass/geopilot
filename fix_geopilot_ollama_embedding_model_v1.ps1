$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$EnvFile = Join-Path $Root ".env"
if (!(Test-Path $EnvFile)) {
    throw ".env file not found in project root."
}

Write-Host "============================================================"
Write-Host "GeoPilot Ollama Embedding Model Fix V1"
Write-Host "nomic-embed-text -> embeddinggemma"
Write-Host "NO SOURCE CHANGE / NO DB WRITE / NO MIGRATION"
Write-Host "============================================================"

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root "artifacts\embedding_model_fix_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $EnvFile (Join-Path $Backup ".env") -Force
Write-Host "BACKUP: $Backup"

Write-Host "[1] Pre-change effective configuration"
docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); print('embedding_provider=',s.embedding_provider); print('ollama_embedding_model=',s.ollama_embedding_model); print('openai_embedding_model_configured=',bool(s.openai_embedding_model))"
if ($LASTEXITCODE -ne 0) { throw "Could not read current embedding configuration." }

Write-Host "[2] Update only OLLAMA_EMBEDDING_MODEL in .env"
$Text = Get-Content $EnvFile -Raw
if ($Text -match '(?m)^\s*OLLAMA_EMBEDDING_MODEL\s*=') {
    $Text = [regex]::Replace(
        $Text,
        '(?m)^\s*OLLAMA_EMBEDDING_MODEL\s*=.*$',
        'OLLAMA_EMBEDDING_MODEL=embeddinggemma',
        1
    )
} else {
    if (-not $Text.EndsWith("`n")) { $Text += "`r`n" }
    $Text += "OLLAMA_EMBEDDING_MODEL=embeddinggemma`r`n"
}
Set-Content -Path $EnvFile -Value $Text -Encoding UTF8
Write-Host "OLLAMA_EMBEDDING_MODEL updated: embeddinggemma"

Write-Host "[3] Recreate backend only so env_file is reloaded"
docker compose up -d --no-deps --force-recreate backend
if ($LASTEXITCODE -ne 0) {
    Copy-Item (Join-Path $Backup ".env") $EnvFile -Force
    throw "Backend recreate failed. .env restored from backup."
}

Write-Host "[4] Wait for backend health"
$Healthy = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    $Status = docker inspect --format='{{.State.Health.Status}}' geopilot-v7-backend 2>$null
    if ($LASTEXITCODE -eq 0 -and $Status -eq "healthy") {
        $Healthy = $true
        break
    }
}
if (-not $Healthy) {
    throw "Backend did not become healthy within expected time."
}
Write-Host "backend_health=healthy"

Write-Host "[5] Verify effective runtime model"
docker compose exec -T backend python -c "from app.core.config import get_settings; s=get_settings(); assert s.ollama_embedding_model=='embeddinggemma'; print('runtime_ollama_embedding_model=',s.ollama_embedding_model)"
if ($LASTEXITCODE -ne 0) { throw "Runtime model verification failed." }

Write-Host "[6] Direct Ollama /api/embed verification through backend network path"
docker compose exec -T backend python -c "import httpx; from app.core.config import get_settings; s=get_settings(); r=httpx.post(s.ollama_base_url.rstrip('/')+'/api/embed',json={'model':s.ollama_embedding_model,'input':['GeoPilot embedding runtime verification']},timeout=60); print('status=',r.status_code); r.raise_for_status(); v=r.json().get('embeddings') or []; assert v and len(v[0])==768; print('vector_count=',len(v)); print('dimension=',len(v[0]))"
if ($LASTEXITCODE -ne 0) { throw "Live Ollama embedding verification failed." }

Write-Host "[7] GeoPilot embedding provider verification"
docker compose exec -T backend python -c "from app.services.embedding_providers import embed_with_fallback; b=embed_with_fallback(['GeoPilot provider verification']); print('provider=',b.provider); print('model=',b.model); print('vector_count=',len(b.vectors)); print('dimension=',len(b.vectors[0])); assert b.provider=='ollama'; assert len(b.vectors)==1; assert len(b.vectors[0])==768"
if ($LASTEXITCODE -ne 0) { throw "GeoPilot embedding provider verification failed." }

Write-Host "[8] Embedding/index regression"
if (Test-Path "backend\tests\test_document_embedding_index.py") {
    docker compose exec -T backend python -m pytest -q tests/test_document_embedding_index.py
    if ($LASTEXITCODE -ne 0) { throw "Embedding index regression failed." }
}

Write-Host "[9] Service health"
docker compose ps

Write-Host "============================================================"
Write-Host "OLLAMA EMBEDDING MODEL FIX V1 PASS"
Write-Host "============================================================"
Write-Host "Previous configured model: nomic-embed-text"
Write-Host "Effective model: embeddinggemma"
Write-Host "Ollama /api/embed: PASS"
Write-Host "Embedding dimension: 768"
Write-Host "GeoPilot embedding provider: ollama"
Write-Host "OpenAI embedding fallback: UNCHANGED"
Write-Host "Source change: NONE"
Write-Host "DB write: NONE"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "Live acquired-document E2E rerun: READY"
Write-Host "============================================================"
