$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$BackendTargets=@(
  "$Root\backend\app\core\config.py",
  "$Root\backend\app\services\track_b.py",
  "$Root\backend\app\services\track_b_acceptance.py",
  "$Root\backend\app\services\track_b_ai.py",
  "$Root\backend\app\services\track_b_workflow.py"
)
$Frontend="$Root\frontend\src\pages\TrackBWorkspacePage.tsx"
foreach($P in @($BackendTargets + $Frontend)){ if(!(Test-Path $P)){ throw "Missing source file: $P" } }

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\closed_evidence_mode_removal_v1_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
foreach($P in $BackendTargets){ Copy-Item $P (Join-Path $Backup ([IO.Path]::GetFileName($P))) -Force }
Copy-Item $Frontend "$Backup\TrackBWorkspacePage.tsx" -Force
if(Test-Path "$Root\.env"){ Copy-Item "$Root\.env" "$Backup\.env" -Force }
if(Test-Path "$Root\.env.example"){ Copy-Item "$Root\.env.example" "$Backup\.env.example" -Force }
Write-Host "BACKUP: $Backup"

Write-Host "============================================================"
Write-Host "GeoPilot Closed Evidence Mode Removal V1.1"
Write-Host "Recovery for backend-container/frontend-path separation"
Write-Host "============================================================"

try {
  Write-Host "[1] Stage backend patch + verifier"
  Copy-Item "$Root\patch_geopilot_remove_closed_evidence_mode_backend_v1_1.py" "$Root\backend\_remove_closed_evidence_mode_backend_v1_1.py" -Force
  Copy-Item "$Root\verify_geopilot_remove_closed_evidence_mode_backend_v1_1.py" "$Root\backend\_verify_remove_closed_evidence_mode_backend_v1_1.py" -Force

  Write-Host "[2] Apply backend removal inside backend container"
  docker compose exec -T backend python /app/_remove_closed_evidence_mode_backend_v1_1.py
  if($LASTEXITCODE-ne 0){ throw "Backend removal patch failed." }

  Write-Host "[3] Apply frontend removal locally"
  & "$Root\patch_geopilot_remove_closed_evidence_mode_frontend_v1_1.ps1" -Path $Frontend
  if($LASTEXITCODE-ne 0){ throw "Frontend removal patch failed." }

  Write-Host "[4] Remove TRACK_B_COMPETITION_MODE from env files"
  foreach($EnvPath in @("$Root\.env","$Root\.env.example")){
    if(Test-Path $EnvPath){
      $t=Get-Content $EnvPath -Raw
      $t=[regex]::Replace($t,'(?m)^\s*TRACK_B_COMPETITION_MODE\s*=.*(?:\r?\n|$)','')
      Set-Content -Path $EnvPath -Value $t -Encoding UTF8
      Write-Host "cleaned: $EnvPath"
    }
  }

  Write-Host "[5] Backend syntax checks"
  docker compose exec -T backend python -m py_compile app/core/config.py app/services/track_b.py app/services/track_b_acceptance.py app/services/track_b_ai.py app/services/track_b_workflow.py
  if($LASTEXITCODE-ne 0){ throw "Backend syntax check failed." }

  Write-Host "[6] Backend removal verification"
  docker compose exec -T backend python /app/_verify_remove_closed_evidence_mode_backend_v1_1.py
  if($LASTEXITCODE-ne 0){ throw "Backend removal verification failed." }

  Write-Host "[7] Frontend removal verification"
  $FrontText=Get-Content $Frontend -Raw
  foreach($Forbidden in @(
    "CLOSED EVIDENCE MODE",
    "external acquisition disabled",
    "ORGANIZER_ONLY",
    "organizer-only before/after pairs",
    "Register matching organizer-only"
  )){
    if($FrontText -match [regex]::Escape($Forbidden)){ throw "Frontend marker remains: $Forbidden" }
  }
  Write-Host "frontend_closed_mode_markers=NONE"

  Write-Host "[8] Frontend production build"
  docker compose exec -T frontend npm run build
  if($LASTEXITCODE-ne 0){ throw "Frontend build failed." }

  Write-Host "[9] Track B regressions"
  foreach($T in @(
    "tests/test_track_b.py",
    "tests/test_track_b_ai.py",
    "tests/test_track_b_acceptance.py",
    "tests/test_track_b_workflow.py"
  )){
    if(Test-Path "$Root\backend\$T"){
      docker compose exec -T backend python -m pytest -q $T
      if($LASTEXITCODE-ne 0){ throw "Regression failed: $T" }
    }
  }

  Write-Host "[10] Planning/document regressions"
  foreach($T in @(
    "tests/test_planning_document_auto_research.py",
    "tests/test_document_retrieval.py",
    "tests/test_planning_document_acquisition.py"
  )){
    if(Test-Path "$Root\backend\$T"){
      docker compose exec -T backend python -m pytest -q $T
      if($LASTEXITCODE-ne 0){ throw "Regression failed: $T" }
    }
  }

  Write-Host "[11] Recreate backend + restart frontend"
  docker compose up -d --no-deps --force-recreate backend
  if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }
  docker compose restart frontend
  if($LASTEXITCODE-ne 0){ throw "Frontend restart failed." }

  Start-Sleep -Seconds 5
  Write-Host "[12] Service health"
  docker compose ps

  Write-Host "============================================================"
  Write-Host "CLOSED EVIDENCE MODE REMOVAL V1.1 PASS"
  Write-Host "============================================================"
  Write-Host "TRACK_B_COMPETITION_MODE setting: REMOVED"
  Write-Host "Organizer-only external acquisition gate: REMOVED"
  Write-Host "Closed-evidence AI scope rejection: REMOVED"
  Write-Host "Closed-evidence prompt terminology: REMOVED"
  Write-Host "Closed-evidence acceptance blocker: REMOVED"
  Write-Host "Closed-evidence UI badge: REMOVED"
  Write-Host "Organizer-only UI wording: REMOVED"
  Write-Host "Arbitrary factual invention: STILL FORBIDDEN"
  Write-Host "Numeric grounding: PRESERVED"
  Write-Host "Evidence provenance: PRESERVED"
  Write-Host "Professional-review boundary: PRESERVED"
  Write-Host "Auto Research RT/RSN/RKK/GPP: PRESERVED"
  Write-Host "DB schema change: NONE"
  Write-Host "Migration: NONE"
  Write-Host "============================================================"
}
catch {
  Write-Host "REMOVAL FAILED - restoring source/env backup."
  Copy-Item "$Backup\config.py" "$Root\backend\app\core\config.py" -Force
  Copy-Item "$Backup\track_b.py" "$Root\backend\app\services\track_b.py" -Force
  Copy-Item "$Backup\track_b_acceptance.py" "$Root\backend\app\services\track_b_acceptance.py" -Force
  Copy-Item "$Backup\track_b_ai.py" "$Root\backend\app\services\track_b_ai.py" -Force
  Copy-Item "$Backup\track_b_workflow.py" "$Root\backend\app\services\track_b_workflow.py" -Force
  Copy-Item "$Backup\TrackBWorkspacePage.tsx" $Frontend -Force
  if(Test-Path "$Backup\.env"){ Copy-Item "$Backup\.env" "$Root\.env" -Force }
  if(Test-Path "$Backup\.env.example"){ Copy-Item "$Backup\.env.example" "$Root\.env.example" -Force }
  throw
}
finally {
  Remove-Item "$Root\backend\_remove_closed_evidence_mode_backend_v1_1.py" -Force -ErrorAction SilentlyContinue
  Remove-Item "$Root\backend\_verify_remove_closed_evidence_mode_backend_v1_1.py" -Force -ErrorAction SilentlyContinue
}
