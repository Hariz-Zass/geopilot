$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Api="$Root\backend\app\api\v1\track_b.py"
$Test="$Root\backend\tests\test_track_b_planning_site_lifecycle_bridge_v1_2.py"

if(!(Test-Path $Api)){ throw "Missing required file: $Api" }

Write-Host "============================================================"
Write-Host "GeoPilot Track B Planning Site Lifecycle Bridge V1.2"
Write-Host "Fix misplaced site_state argument in compact helper"
Write-Host "NO DB UPDATE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\track_b_planning_site_lifecycle_bridge_v1_2_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Api "$Backup\track_b_api.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_track_b_planning_site_lifecycle_bridge_v1_2.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Preflight live wiring gate"
    $t=Get-Content $Api -Raw

    $bad='request=PlanningRunCreate(question=question, development_intent=None, site_state=SiteState.AVAILABLE)'
    if(-not $t.Contains($bad)){
        throw "Expected misplaced site_state argument not found."
    }

    if($t -notmatch 'execute_planning_run\(.*site_state=SiteState\.AVAILABLE'){
        throw "Expected execute_planning_run AVAILABLE override not found."
    }

    Write-Host "misplaced_create_site_state=CONFIRMED"
    Write-Host "execute_site_state_override=PRESERVED"

    Write-Host "[1] Move site_state from PlanningRunCreate to create_planning_run"
    $good='request=PlanningRunCreate(question=question, development_intent=None), site_state=SiteState.AVAILABLE'
    $t=$t.Replace($bad,$good)
    Set-Content $Api $t -Encoding UTF8

    Write-Host "[2] Static source verification"
    $t=Get-Content $Api -Raw

    if($t.Contains($bad)){
        throw "Misplaced site_state remains inside PlanningRunCreate."
    }

    if(-not $t.Contains($good)){
        throw "Correct create_planning_run AVAILABLE argument not found."
    }

    $helperStart=$t.IndexOf("def _run_track_b_planning_question(")
    if($helperStart -lt 0){ throw "Track B helper not found." }
    $helperEnd=$t.IndexOf("`n`n@router.post",$helperStart)
    if($helperEnd -lt 0){ throw "Track B helper end not found." }
    $helper=$t.Substring($helperStart,$helperEnd-$helperStart)

    $count=([regex]::Matches($helper,'site_state=SiteState\.AVAILABLE')).Count
    if($count -ne 2){
        throw "Expected exactly 2 AVAILABLE overrides in helper, found $count."
    }

    Write-Host "helper_available_override_count=2"

    Write-Host "[3] Install focused regression"
    $testText=@'
from pathlib import Path
import inspect

from app.schemas.planning_run import PlanningRunCreate
from app.services.isolation import SiteState
from app.services.planning_runs import create_planning_run
from app.services.planning_orchestrator import execute_planning_run


def test_planning_run_create_has_no_site_state_field():
    assert "site_state" not in PlanningRunCreate.model_fields


def test_track_b_helper_passes_available_to_service_not_schema():
    text = Path("app/api/v1/track_b.py").read_text(encoding="utf-8-sig")
    start = text.index("def _run_track_b_planning_question(")
    end = text.index("\n\n@router.post", start)
    block = text[start:end]

    assert "PlanningRunCreate(question=question, development_intent=None, site_state=" not in block
    assert "PlanningRunCreate(question=question, development_intent=None), site_state=SiteState.AVAILABLE" in block
    assert "execute_planning_run(" in block
    assert block.count("site_state=SiteState.AVAILABLE") == 2


def test_service_defaults_remain_active():
    assert inspect.signature(create_planning_run).parameters["site_state"].default is SiteState.ACTIVE
    assert inspect.signature(execute_planning_run).parameters["site_state"].default is SiteState.ACTIVE
'@
    Set-Content $Test $testText -Encoding UTF8

    Write-Host "[4] Syntax checks"
    docker compose exec -T backend python -m py_compile app/api/v1/track_b.py tests/test_track_b_planning_site_lifecycle_bridge_v1_2.py
    if($LASTEXITCODE-ne 0){ throw "Syntax check failed." }

    Write-Host "[5] Focused lifecycle wiring regression"
    docker compose exec -T backend python -m pytest -q tests/test_track_b_planning_site_lifecycle_bridge_v1_2.py
    if($LASTEXITCODE-ne 0){ throw "Focused lifecycle wiring regression failed." }

    Write-Host "[6] Preserve V1.1 lifecycle + dispatcher regressions"
    foreach($T in @(
        "tests/test_track_b_planning_site_lifecycle_bridge_v1_1.py",
        "tests/test_track_b_planning_question_dispatcher_v1.py",
        "tests/test_track_b_planning_question_dispatcher_manifest_v1_2.py"
    )){
        if(Test-Path "$Root\backend\$T"){
            docker compose exec -T backend python -m pytest -q $T
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $T" }
        }
    }

    Write-Host "[7] Runtime helper verification before restart"
    docker compose exec -T backend python -c "import inspect; import app.api.v1.track_b as tb; from app.schemas.planning_run import PlanningRunCreate; s=inspect.getsource(tb._run_track_b_planning_question); assert 'site_state=SiteState.AVAILABLE' in s; assert s.count('site_state=SiteState.AVAILABLE')==2; assert 'site_state' not in PlanningRunCreate.model_fields; print(s); print('runtime_helper_contract=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Runtime helper verification failed." }

    Write-Host "[8] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[9] Backend health"
    docker compose ps backend

    Write-Host "[10] Final runtime verification"
    docker compose exec -T backend python -c "import inspect; import app.api.v1.track_b as tb; from app.schemas.planning_run import PlanningRunCreate; s=inspect.getsource(tb._run_track_b_planning_question); assert 'PlanningRunCreate(question=question, development_intent=None, site_state=' not in s; assert 'PlanningRunCreate(question=question, development_intent=None), site_state=SiteState.AVAILABLE' in s; assert s.count('site_state=SiteState.AVAILABLE')==2; assert 'site_state' not in PlanningRunCreate.model_fields; print('runtime_lifecycle_wiring=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Final runtime verification failed." }

    Write-Host "============================================================"
    Write-Host "TRACK B PLANNING SITE LIFECYCLE BRIDGE V1.2 PASS"
    Write-Host "============================================================"
    Write-Host "PlanningRunCreate site_state field: NOT PRESENT (CONFIRMED)"
    Write-Host "Misplaced site_state inside request schema: FIXED"
    Write-Host "create_planning_run site_state=AVAILABLE: ENABLED"
    Write-Host "execute_planning_run site_state=AVAILABLE: PRESERVED"
    Write-Host "Normal PlanningRun default Site requirement: ACTIVE (PRESERVED)"
    Write-Host "Archived-site rejection: PRESERVED"
    Write-Host "Site DB flags changed: NONE"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend change: NONE"
    Write-Host "Next gate: RETEST LIVE GPP QUESTION"
    Write-Host "============================================================"
}
catch {
    Write-Host "REPAIR FAILED - restoring API/test backup."
    Copy-Item "$Backup\track_b_api.py" $Api -Force

    if(Test-Path "$Backup\test_track_b_planning_site_lifecycle_bridge_v1_2.py"){
        Copy-Item "$Backup\test_track_b_planning_site_lifecycle_bridge_v1_2.py" $Test -Force
    } else {
        Remove-Item $Test -Force -ErrorAction SilentlyContinue
    }
    throw
}
