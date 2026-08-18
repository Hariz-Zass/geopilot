$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service="$Root\backend\app\services\planning_document_auto_research.py"
$Orchestrator="$Root\backend\app\services\planning_orchestrator.py"
$Test="$Root\backend\tests\test_planning_document_auto_research.py"

foreach($P in @(
  "$Root\planning_document_auto_research_v1.py",
  "$Root\patch_geopilot_auto_research_question_router_v1.py",
  "$Root\test_geopilot_planning_document_auto_research_v1.py"
)){
  if(!(Test-Path $P)){ throw "Missing installer helper: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Auto Research Question Router V1"
Write-Host "Question -> official RT/RSN/RKK/GPP -> ingest/index -> documents.search"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\auto_research_question_router_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Orchestrator "$Backup\planning_orchestrator.py"
if(Test-Path $Service){ Copy-Item $Service "$Backup\planning_document_auto_research.py" }
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_planning_document_auto_research.py" }
Write-Host "BACKUP: $Backup"

try {
  Write-Host "[1] Install bounded auto-research service"
  Copy-Item "$Root\planning_document_auto_research_v1.py" $Service -Force

  Write-Host "[2] Wire existing documents.search flow"
  Copy-Item "$Root\patch_geopilot_auto_research_question_router_v1.py" "$Root\backend\_auto_research_router_patch_v1.py" -Force
  docker compose exec -T backend python /app/_auto_research_router_patch_v1.py
  if($LASTEXITCODE-ne 0){ throw "Orchestrator wiring failed." }

  Write-Host "[3] Install focused tests"
  Copy-Item "$Root\test_geopilot_planning_document_auto_research_v1.py" $Test -Force

  Write-Host "[4] Syntax checks"
  docker compose exec -T backend python -m py_compile app/services/planning_document_auto_research.py app/services/planning_orchestrator.py tests/test_planning_document_auto_research.py
  if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

  Write-Host "[5] Focused auto-research tests"
  docker compose exec -T backend python -m pytest -q tests/test_planning_document_auto_research.py
  if($LASTEXITCODE-ne 0){ throw "Focused auto-research tests failed." }

  Write-Host "[6] Router regression"
  docker compose exec -T backend python -m pytest -q tests/test_data_requirement_router.py
  if($LASTEXITCODE-ne 0){ throw "Data requirement router regression failed." }

  Write-Host "[7] Existing acquisition + retrieval regression"
  docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py tests/test_document_retrieval.py
  if($LASTEXITCODE-ne 0){ throw "Acquisition/retrieval regression failed." }

  Write-Host "[8] Structural verification"
  $Verify="$Root\backend\_verify_auto_research_router_v1.py"
  @'
import inspect
from app.services.planning_document_auto_research import infer_document_classes
import app.services.planning_orchestrator as o

src = inspect.getsource(o.execute_planning_run)
assert "AUTO_RESEARCH_QUESTION_ROUTER_V1" in src
assert "auto_research_planning_documents(" in src
classes = infer_document_classes(
    "berapa densiti dalam rancangan tempatan dan GPP?"
)
assert "RT" in classes and "GPP" in classes
print("auto_research_service=PASS")
print("orchestrator_wiring=PASS")
print("density_classes=", classes)
'@ | Set-Content -Path $Verify -Encoding UTF8

  try {
    docker compose exec -T backend python /app/_verify_auto_research_router_v1.py
    if($LASTEXITCODE-ne 0){ throw "Structural verification failed." }
  }
  finally {
    Remove-Item $Verify -Force -ErrorAction SilentlyContinue
  }

  Write-Host "[9] Service health"
  docker compose ps

  Write-Host "============================================================"
  Write-Host "AUTO RESEARCH QUESTION ROUTER V1 PASS"
  Write-Host "============================================================"
  Write-Host "Question-driven planning document research: ENABLED"
  Write-Host "GPP auto discovery/acquisition: ENABLED"
  Write-Host "RT auto discovery/acquisition: ENABLED when jurisdiction is known"
  Write-Host "RSN auto discovery/acquisition: ENABLED when jurisdiction is known"
  Write-Host "RKK auto discovery/acquisition: ENABLED when jurisdiction is known"
  Write-Host "RFN automatic acquisition: FAIL-CLOSED"
  Write-Host "Existing indexed documents reused: YES"
  Write-Host "Duplicate source/checksum suppression: ENABLED"
  Write-Host "Existing immutable ingest/OCR/chunk/index: REUSED"
  Write-Host "Existing documents.search evidence flow: PRESERVED"
  Write-Host "Unverified statutory effect: NEVER PROMOTED"
  Write-Host "OpenAI/Ollama provider configuration: UNCHANGED"
  Write-Host "Migration: NONE"
  Write-Host "Frontend change: NONE"
  Write-Host "Live question E2E: NEXT GATE"
  Write-Host "============================================================"
}
catch {
  Write-Host "INSTALL FAILED - restoring previous source."
  Copy-Item "$Backup\planning_orchestrator.py" $Orchestrator -Force

  if(Test-Path "$Backup\planning_document_auto_research.py"){
    Copy-Item "$Backup\planning_document_auto_research.py" $Service -Force
  } else {
    Remove-Item $Service -Force -ErrorAction SilentlyContinue
  }

  if(Test-Path "$Backup\test_planning_document_auto_research.py"){
    Copy-Item "$Backup\test_planning_document_auto_research.py" $Test -Force
  } else {
    Remove-Item $Test -Force -ErrorAction SilentlyContinue
  }

  throw
}
finally {
  Remove-Item "$Root\backend\_auto_research_router_patch_v1.py" -Force -ErrorAction SilentlyContinue
}
