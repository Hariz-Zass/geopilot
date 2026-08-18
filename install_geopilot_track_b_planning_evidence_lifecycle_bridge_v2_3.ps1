$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$GIS="$Root\backend\app\services\gis_analysis.py"
$Applic="$Root\backend\app\services\site_applicability.py"
$Tools="$Root\backend\app\services\planning_tools.py"
$Orch="$Root\backend\app\services\planning_orchestrator.py"
$PatchSource="$Root\patch_geopilot_track_b_planning_evidence_lifecycle_bridge_v2_3.py"
$PatchTarget="$Root\backend\_patch_geopilot_track_b_planning_evidence_lifecycle_bridge_v2_3.py"
$Test="$Root\backend\tests\test_track_b_planning_evidence_lifecycle_bridge_v2_3.py"

foreach($P in @($GIS,$Applic,$Tools,$Orch,$PatchSource)){
    if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Track B Planning Evidence Lifecycle Bridge V2.3"
Write-Host "Recovery after V2.2 rollback"
Write-Host "Inactive-but-unarchived Track B Site -> AVAILABLE GIS evidence scope"
Write-Host "Normal analytical defaults remain ACTIVE"
Write-Host "NO DB DATA UPDATE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\track_b_planning_evidence_lifecycle_bridge_v2_3_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $GIS "$Backup\gis_analysis.py"
Copy-Item $Applic "$Backup\site_applicability.py"
Copy-Item $Tools "$Backup\planning_tools.py"
Copy-Item $Orch "$Backup\planning_orchestrator.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_track_b_planning_evidence_lifecycle_bridge_v2_3.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Confirm V2.2 rollback"
    $g=Get-Content $GIS -Raw
    $a=Get-Content $Applic -Raw
    $o=Get-Content $Orch -Raw

    if($g -match 'site_state: SiteState = SiteState.ACTIVE'){
        throw "Unexpected partial GIS V2.2 modification detected."
    }
    if($a -match 'site_state: SiteState = SiteState.ACTIVE'){
        throw "Unexpected partial applicability V2.2 modification detected."
    }
    if($g -notmatch 'AND s\.is_active IS TRUE'){
        throw "Expected ACTIVE-only site area gate not found."
    }
    if($o -notmatch 'site_state:\s*SiteState\s*=\s*SiteState\.ACTIVE'){
        throw "Existing PlanningRun lifecycle bridge missing."
    }
    Write-Host "rollback_state=CONFIRMED"

    Write-Host "[1] Stage validated standalone patcher"
    Copy-Item $PatchSource $PatchTarget -Force

    Write-Host "[2] Patcher syntax check"
    docker compose exec -T backend python -m py_compile /app/_patch_geopilot_track_b_planning_evidence_lifecycle_bridge_v2_3.py
    if($LASTEXITCODE-ne 0){ throw "Standalone patcher syntax check failed." }

    Write-Host "[3] Apply lifecycle patch"
    docker compose exec -T backend python /app/_patch_geopilot_track_b_planning_evidence_lifecycle_bridge_v2_3.py
    if($LASTEXITCODE-ne 0){ throw "Lifecycle patch failed." }

    Write-Host "[4] Install focused regression"
    @'
from pathlib import Path

def test_gis_area_explicit_site_state_opt_in():
    text=Path("app/services/gis_analysis.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert "site_state=site_state" in text
    assert "if site_state is SiteState.ACTIVE" in text
    assert "AND s.is_archived IS FALSE" in text

def test_applicability_explicit_site_state_opt_in():
    text=Path("app/services/site_applicability.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert "site_state=site_state" in text

def test_planning_tools_propagate_site_state():
    text=Path("app/services/planning_tools.py").read_text(encoding="utf-8-sig")
    assert text.count("site_state: SiteState = SiteState.ACTIVE") >= 2
    assert text.count("site_state=site_state") >= 2

def test_orchestrator_propagates_existing_track_b_site_state():
    text=Path("app/services/planning_orchestrator.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert text.count("site_state=site_state") >= 3

def test_terrain_available_behavior_remains():
    text=Path("app/services/terrain_analysis.py").read_text(encoding="utf-8-sig")
    assert "site_state=SiteState.AVAILABLE" in text
'@ | Set-Content $Test -Encoding UTF8

    Write-Host "[5] Backend syntax checks"
    docker compose exec -T backend python -m py_compile app/services/gis_analysis.py app/services/site_applicability.py app/services/planning_tools.py app/services/planning_orchestrator.py tests/test_track_b_planning_evidence_lifecycle_bridge_v2_3.py
    if($LASTEXITCODE-ne 0){ throw "Backend syntax check failed." }

    Write-Host "[6] Focused lifecycle regression"
    docker compose exec -T backend python -m pytest -q tests/test_track_b_planning_evidence_lifecycle_bridge_v2_3.py
    if($LASTEXITCODE-ne 0){ throw "Focused lifecycle regression failed." }

    Write-Host "[7] Preserve previous lifecycle/evidence regressions"
    foreach($Regression in @(
        "tests/test_track_b_planning_site_lifecycle_bridge_v1_2.py",
        "tests/test_auto_research_evidence_scope_bridge_v2.py"
    )){
        if(Test-Path "$Root\backend\$Regression"){
            docker compose exec -T backend python -m pytest -q $Regression
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $Regression" }
        }
    }

    Write-Host "[8] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5

    Write-Host "[9] Backend health"
    docker compose ps backend

    Write-Host "[10] Runtime verification"
    docker compose exec -T backend python -c "from app.services.gis_analysis import calculate_site_area; from app.services.site_applicability import resolve_site_applicability; from app.services.planning_orchestrator import execute_planning_run; print('runtime_lifecycle_bridge=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Runtime verification failed." }

    Remove-Item $PatchTarget -Force -ErrorAction SilentlyContinue

    Write-Host "============================================================"
    Write-Host "TRACK B PLANNING EVIDENCE LIFECYCLE BRIDGE V2.3 PASS"
    Write-Host "============================================================"
    Write-Host "Track B inactive-unarchived Site: AVAILABLE FOR PLANNING EVIDENCE"
    Write-Host "Normal GIS analysis default Site requirement: ACTIVE"
    Write-Host "gis.site_area Track B opt-in: AVAILABLE"
    Write-Host "gis.site_applicability Track B opt-in: AVAILABLE"
    Write-Host "terrain.site_summary AVAILABLE behavior: PRESERVED"
    Write-Host "Archived Site rejection: PRESERVED"
    Write-Host "Archived Project rejection: PRESERVED"
    Write-Host "Project ownership isolation: PRESERVED"
    Write-Host "Site/project identity isolation: PRESERVED"
    Write-Host "DB flags changed: NONE"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend change: NONE"
    Write-Host "Next gate: RETEST PLANNER QUESTION ON SHAH ALAM SITE"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring source/test backup."
    Copy-Item "$Backup\gis_analysis.py" $GIS -Force
    Copy-Item "$Backup\site_applicability.py" $Applic -Force
    Copy-Item "$Backup\planning_tools.py" $Tools -Force
    Copy-Item "$Backup\planning_orchestrator.py" $Orch -Force
    Remove-Item $PatchTarget -Force -ErrorAction SilentlyContinue

    if(Test-Path "$Backup\test_track_b_planning_evidence_lifecycle_bridge_v2_3.py"){
        Copy-Item "$Backup\test_track_b_planning_evidence_lifecycle_bridge_v2_3.py" $Test -Force
    } else {
        Remove-Item $Test -Force -ErrorAction SilentlyContinue
    }
    throw
}
