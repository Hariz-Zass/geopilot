$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Target="$Root\backend\app\services\site_applicability.py"
$PatchSource="$Root\patch_geopilot_site_applicability_available_sql_bridge_v1.py"
$PatchTarget="$Root\backend\_patch_geopilot_site_applicability_available_sql_bridge_v1.py"
$Test="$Root\backend\tests\test_site_applicability_available_sql_bridge_v1.py"

foreach($P in @($Target,$PatchSource)){
    if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Site Applicability AVAILABLE SQL Bridge V1"
Write-Host "Track B AVAILABLE site -> applicability SQL"
Write-Host "Normal ACTIVE default preserved"
Write-Host "NO DB DATA UPDATE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\site_applicability_available_sql_bridge_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Target "$Backup\site_applicability.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_site_applicability_available_sql_bridge_v1.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Preflight"
    $t=Get-Content $Target -Raw

    if($t -notmatch 'site_state:\s*SiteState\s*=\s*SiteState\.ACTIVE'){
        throw "Existing SiteState lifecycle bridge missing."
    }
    if($t -notmatch 'AND s\.is_active IS TRUE'){
        throw "Expected hardcoded ACTIVE SQL gate not found."
    }
    if($t -match ':require_active'){
        throw "AVAILABLE SQL bridge already appears installed."
    }
    Write-Host "preflight_state=CONFIRMED"

    Write-Host "[1] Stage validated patcher"
    Copy-Item $PatchSource $PatchTarget -Force

    Write-Host "[2] Patcher syntax check"
    docker compose exec -T backend python -m py_compile /app/_patch_geopilot_site_applicability_available_sql_bridge_v1.py
    if($LASTEXITCODE-ne 0){ throw "Patcher syntax check failed." }

    Write-Host "[3] Apply SQL lifecycle bridge"
    docker compose exec -T backend python /app/_patch_geopilot_site_applicability_available_sql_bridge_v1.py
    if($LASTEXITCODE-ne 0){ throw "SQL lifecycle patch failed." }

    Write-Host "[4] Install focused regressions"
@'
from pathlib import Path

def test_available_sql_gate_is_parameterized():
    text=Path("app/services/site_applicability.py").read_text(encoding="utf-8-sig")
    assert ":require_active IS FALSE" in text
    assert "OR s.is_active IS TRUE" in text
    assert '"require_active": site_state is SiteState.ACTIVE' in text

def test_archived_site_sql_gate_remains_fail_closed():
    text=Path("app/services/site_applicability.py").read_text(encoding="utf-8-sig")
    assert "AND s.is_archived IS FALSE" in text

def test_python_scope_still_propagates_site_state():
    text=Path("app/services/site_applicability.py").read_text(encoding="utf-8-sig")
    assert "site_state: SiteState = SiteState.ACTIVE" in text
    assert "site_state=site_state" in text
'@ | Set-Content $Test -Encoding UTF8

    Write-Host "[5] Backend syntax checks"
    docker compose exec -T backend python -m py_compile app/services/site_applicability.py tests/test_site_applicability_available_sql_bridge_v1.py
    if($LASTEXITCODE-ne 0){ throw "Backend syntax check failed." }

    Write-Host "[6] Focused SQL bridge regressions"
    docker compose exec -T backend python -m pytest -q tests/test_site_applicability_available_sql_bridge_v1.py
    if($LASTEXITCODE-ne 0){ throw "Focused SQL bridge regression failed." }

    Write-Host "[7] Preserve lifecycle/router/spatial-foundation regressions"
    foreach($Regression in @(
        "tests/test_track_b_planning_evidence_lifecycle_bridge_v2_3.py",
        "tests/test_planning_question_multi_evidence_router_v1_2.py",
        "tests/test_planning_spatial_evidence_foundation_v1.py",
        "tests/test_auto_research_evidence_scope_bridge_v2.py"
    )){
        if(Test-Path "$Root\backend\$Regression"){
            docker compose exec -T backend python -m pytest -q $Regression
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $Regression" }
        }
    }

    Write-Host "[8] Static contract verification"
    $t=Get-Content $Target -Raw
    if($t -notmatch ':require_active IS FALSE'){ throw "Parameterized ACTIVE gate missing." }
    if($t -notmatch '"require_active": site_state is SiteState\.ACTIVE'){ throw "require_active binding missing." }
    if($t -notmatch 'AND s\.is_archived IS FALSE'){ throw "Archived-site gate missing." }
    Write-Host "sql_lifecycle_contract=PASS"

    Write-Host "[9] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5
    Write-Host "[10] Backend health"
    docker compose ps backend

    Write-Host "[11] Runtime import verification"
    docker compose exec -T backend python -c "from app.services.site_applicability import resolve_site_applicability; print('runtime_site_applicability_sql_bridge=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Runtime import verification failed." }

    Remove-Item $PatchTarget -Force -ErrorAction SilentlyContinue

    Write-Host "============================================================"
    Write-Host "SITE APPLICABILITY AVAILABLE SQL BRIDGE V1 PASS"
    Write-Host "============================================================"
    Write-Host "Track B AVAILABLE site in applicability SQL: ENABLED"
    Write-Host "Normal ACTIVE default: PRESERVED"
    Write-Host "Archived Site rejection: PRESERVED"
    Write-Host "Project/site identity filters: PRESERVED"
    Write-Host "GIS layer/feature filters: PRESERVED"
    Write-Host "DB data change: NONE"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend change: NONE"
    Write-Host "Next gate: RERUN PLANNING SPATIAL ACCEPTANCE FIXTURE"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring site_applicability.py/test backup."
    Copy-Item "$Backup\site_applicability.py" $Target -Force
    Remove-Item $PatchTarget -Force -ErrorAction SilentlyContinue

    if(Test-Path "$Backup\test_site_applicability_available_sql_bridge_v1.py"){
        Copy-Item "$Backup\test_site_applicability_available_sql_bridge_v1.py" $Test -Force
    } else {
        Remove-Item $Test -Force -ErrorAction SilentlyContinue
    }
    throw
}
