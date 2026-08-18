$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Orchestrator="$Root\backend\app\services\planning_orchestrator.py"
$PatchHelper="$Root\patch_geopilot_auto_research_evidence_bridge_v1.py"
$TestHelper="$Root\test_geopilot_auto_research_evidence_bridge_v1.py"
$VerifyHelper="$Root\verify_geopilot_auto_research_evidence_bridge_v1.py"
$FocusedTest="$Root\backend\tests\test_auto_research_evidence_bridge_v1.py"

foreach($P in @($Orchestrator,$PatchHelper,$TestHelper,$VerifyHelper)){
  if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Auto Research Evidence Bridge V1"
Write-Host "Fix auto-acquired documents being suppressed by applicability gate"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\auto_research_evidence_bridge_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Orchestrator "$Backup\planning_orchestrator.py"
if(Test-Path $FocusedTest){ Copy-Item $FocusedTest "$Backup\test_auto_research_evidence_bridge_v1.py" }
Write-Host "BACKUP: $Backup"

try {
  Write-Host "[1] Pre-change structural diagnosis"
  $Before=Get-Content $Orchestrator -Raw
  if($Before -notmatch "AUTO_RESEARCH_QUESTION_ROUTER_V1"){
    throw "Auto Research Question Router V1 is not installed."
  }
  if($Before -match "AUTO_RESEARCH_EVIDENCE_BRIDGE_V1"){
    throw "Evidence Bridge V1 already appears installed. Stop to avoid double patch."
  }
  if($Before -notmatch "applicable_document_ids = \[\]"){
    throw "Expected empty applicability gate not found. Stop for inspection."
  }
  Write-Host "diagnosis=EMPTY_APPLICABILITY_GATE_CAN_SUPPRESS_AUTO_RESEARCH_DOCUMENTS"

  Write-Host "[2] Apply evidence-flow bridge"
  Copy-Item $PatchHelper "$Root\backend\_auto_research_evidence_bridge_patch_v1.py" -Force
  docker compose exec -T backend python /app/_auto_research_evidence_bridge_patch_v1.py
  if($LASTEXITCODE-ne 0){ throw "Evidence bridge patch failed." }

  Write-Host "[3] Install focused tests"
  Copy-Item $TestHelper $FocusedTest -Force

  Write-Host "[4] Syntax checks"
  docker compose exec -T backend python -m py_compile app/services/planning_orchestrator.py tests/test_auto_research_evidence_bridge_v1.py
  if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

  Write-Host "[5] Focused bridge tests"
  docker compose exec -T backend python -m pytest -q tests/test_auto_research_evidence_bridge_v1.py
  if($LASTEXITCODE-ne 0){ throw "Focused bridge tests failed." }

  Write-Host "[6] Auto-research regression"
  if(!(Test-Path "$Root\backend\tests\test_planning_document_auto_research.py")){
    throw "Expected Auto Research V1 test file is missing."
  }
  docker compose exec -T backend python -m pytest -q tests/test_planning_document_auto_research.py
  if($LASTEXITCODE-ne 0){ throw "Auto-research regression failed." }

  Write-Host "[7] Acquisition + retrieval regression"
  docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py tests/test_document_retrieval.py
  if($LASTEXITCODE-ne 0){ throw "Acquisition/retrieval regression failed." }

  Write-Host "[8] Router regression"
  if(Test-Path "$Root\backend\tests\test_data_requirement_router.py"){
    docker compose exec -T backend python -m pytest -q tests/test_data_requirement_router.py
    if($LASTEXITCODE-ne 0){ throw "Router regression failed." }
  }

  Write-Host "[9] Structural verification"
  Copy-Item $VerifyHelper "$Root\backend\_verify_auto_research_evidence_bridge_v1.py" -Force
  docker compose exec -T backend python /app/_verify_auto_research_evidence_bridge_v1.py
  if($LASTEXITCODE-ne 0){ throw "Structural verification failed." }

  Write-Host "[10] Service health"
  docker compose ps

  Write-Host "============================================================"
  Write-Host "AUTO RESEARCH EVIDENCE BRIDGE V1 PASS"
  Write-Host "============================================================"
  Write-Host "Root cause: empty site-applicability gate suppressed auto-researched documents"
  Write-Host "Auto-acquired document IDs -> documents.search: ENABLED"
  Write-Host "Existing applicability-linked document IDs: PRESERVED"
  Write-Host "Auto + applicability document IDs: MERGED"
  Write-Host "No candidate documents: FAIL-CLOSED PRESERVED"
  Write-Host "Site applicability inference from catalogue metadata: FORBIDDEN"
  Write-Host "Document citation/page evidence path: PRESERVED"
  Write-Host "Anti-hallucination boundary: PRESERVED"
  Write-Host "AI provider configuration: UNCHANGED"
  Write-Host "DB schema change: NONE"
  Write-Host "Migration: NONE"
  Write-Host "Frontend change: NONE"
  Write-Host "Live UI GPP E2E retest: NEXT GATE"
  Write-Host "============================================================"
}
catch {
  Write-Host "INSTALL FAILED - restoring previous orchestrator."
  Copy-Item "$Backup\planning_orchestrator.py" $Orchestrator -Force
  if(Test-Path "$Backup\test_auto_research_evidence_bridge_v1.py"){
    Copy-Item "$Backup\test_auto_research_evidence_bridge_v1.py" $FocusedTest -Force
  } else {
    Remove-Item $FocusedTest -Force -ErrorAction SilentlyContinue
  }
  throw
}
finally {
  Remove-Item "$Root\backend\_auto_research_evidence_bridge_patch_v1.py" -Force -ErrorAction SilentlyContinue
  Remove-Item "$Root\backend\_verify_auto_research_evidence_bridge_v1.py" -Force -ErrorAction SilentlyContinue
}
