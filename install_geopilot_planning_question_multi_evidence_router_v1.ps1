$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Router="$Root\backend\app\services\data_requirement_router.py"
$TrackB="$Root\backend\app\api\v1\track_b.py"
$PatchSource="$Root\patch_geopilot_planning_question_multi_evidence_router_v1.py"
$PatchTarget="$Root\backend\_patch_geopilot_planning_question_multi_evidence_router_v1.py"
$Test="$Root\backend\tests\test_planning_question_multi_evidence_router_v1.py"

foreach($P in @($Router,$TrackB,$PatchSource)){
    if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Planning Question Multi-Evidence Router V1"
Write-Host "Mixed area + terrain -> GIS area + terrain evidence"
Write-Host "Pure terrain direct route preserved"
Write-Host "NO DB DATA UPDATE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\planning_question_multi_evidence_router_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Router "$Backup\data_requirement_router.py"
Copy-Item $TrackB "$Backup\track_b.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_planning_question_multi_evidence_router_v1.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Preflight"
    $r=Get-Content $Router -Raw
    $b=Get-Content $TrackB -Raw
    if($r -match 'capability="planning_multi_evidence"'){ throw "Multi-evidence router already installed." }
    if($r -notmatch 'capability="terrain_measurement"'){ throw "Terrain route missing." }
    if($b -notmatch '"documents\.search" in route\.tools'){ throw "Track B planning dispatcher gate missing." }
    Write-Host "preflight_state=CONFIRMED"

    Write-Host "[1] Stage validated patcher"
    Copy-Item $PatchSource $PatchTarget -Force

    Write-Host "[2] Patcher syntax check"
    docker compose exec -T backend python -m py_compile /app/_patch_geopilot_planning_question_multi_evidence_router_v1.py
    if($LASTEXITCODE-ne 0){ throw "Patcher syntax check failed." }

    Write-Host "[3] Apply router + dispatcher patch"
    docker compose exec -T backend python /app/_patch_geopilot_planning_question_multi_evidence_router_v1.py
    if($LASTEXITCODE-ne 0){ throw "Router patch failed." }

    Write-Host "[4] Install focused regressions"
@'
from pathlib import Path
from app.services.data_requirement_router import route_question

def test_mixed_area_and_terrain_routes_to_both_tools():
    q = (
        "Berdasarkan kawasan tapak yang dipilih, apakah keluasan tapak, "
        "keadaan terrain termasuk elevation dan slope?"
    )
    r = route_question(q)
    assert r.state == "planned"
    assert r.capability == "planning_multi_evidence"
    assert r.tools == ("gis.site_area", "terrain.site_summary")

def test_pure_terrain_measurement_preserves_direct_route():
    r = route_question("Berapakah slope maksimum dan elevation purata tapak ini?")
    assert r.capability == "terrain_measurement"
    assert r.tools == ("terrain.site_summary",)

def test_general_area_question_still_uses_site_area():
    r = route_question("Berapakah keluasan tapak ini?")
    assert "gis.site_area" in r.tools

def test_track_b_dispatcher_sends_multi_evidence_to_planning_orchestrator():
    text = Path("app/api/v1/track_b.py").read_text(encoding="utf-8-sig")
    assert 'route.capability == "planning_multi_evidence"' in text
    assert '"documents.search" in route.tools' in text

def test_policy_precedence_is_preserved():
    r = route_question("Apakah garis panduan pembangunan cerun dan slope yang terpakai?")
    assert r.capability == "terrain_policy"
    assert r.tools == ("documents.search",)
'@ | Set-Content $Test -Encoding UTF8

    Write-Host "[5] Backend syntax checks"
    docker compose exec -T backend python -m py_compile app/services/data_requirement_router.py app/api/v1/track_b.py tests/test_planning_question_multi_evidence_router_v1.py
    if($LASTEXITCODE-ne 0){ throw "Backend syntax check failed." }

    Write-Host "[6] Focused multi-evidence regressions"
    docker compose exec -T backend python -m pytest -q tests/test_planning_question_multi_evidence_router_v1.py
    if($LASTEXITCODE-ne 0){ throw "Focused multi-evidence regression failed." }

    Write-Host "[7] Preserve prior regressions"
    foreach($Regression in @(
        "tests/test_track_b_planning_site_lifecycle_bridge_v1_2.py",
        "tests/test_track_b_planning_evidence_lifecycle_bridge_v2_3.py",
        "tests/test_auto_research_evidence_scope_bridge_v2.py",
        "tests/test_track_b_hackathon.py"
    )){
        if(Test-Path "$Root\backend\$Regression"){
            docker compose exec -T backend python -m pytest -q $Regression
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $Regression" }
        }
    }

    Write-Host "[8] Runtime route verification"
    docker compose exec -T backend python -c "from app.services.data_requirement_router import route_question; q='Berdasarkan kawasan tapak yang dipilih, apakah keluasan tapak, keadaan terrain termasuk elevation dan slope, serta apakah implikasi perancangan utama untuk pembangunan di kawasan ini? Gunakan hanya bukti yang tersedia untuk tapak ini dan nyatakan limitation jika data tidak mencukupi.'; r=route_question(q); print('state=',r.state); print('capability=',r.capability); print('tools=',r.tools)"
    if($LASTEXITCODE-ne 0){ throw "Runtime route verification failed." }

    Write-Host "[9] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5
    Write-Host "[10] Backend health"
    docker compose ps backend

    Remove-Item $PatchTarget -Force -ErrorAction SilentlyContinue

    Write-Host "============================================================"
    Write-Host "PLANNING QUESTION MULTI-EVIDENCE ROUTER V1 PASS"
    Write-Host "============================================================"
    Write-Host "Mixed area + terrain routing: ENABLED"
    Write-Host "gis.site_area + terrain.site_summary: COMBINED"
    Write-Host "Pure terrain direct path: PRESERVED"
    Write-Host "Terrain policy document path: PRESERVED"
    Write-Host "Track B multi-evidence -> Planning Orchestrator: ENABLED"
    Write-Host "Lifecycle AVAILABLE bridge: PRESERVED"
    Write-Host "DB flags changed: NONE"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend change: NONE"
    Write-Host "Next gate: RETEST SAME AREA + TERRAIN QUESTION"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring router/dispatcher/test backup."
    Copy-Item "$Backup\data_requirement_router.py" $Router -Force
    Copy-Item "$Backup\track_b.py" $TrackB -Force
    Remove-Item $PatchTarget -Force -ErrorAction SilentlyContinue
    if(Test-Path "$Backup\test_planning_question_multi_evidence_router_v1.py"){
        Copy-Item "$Backup\test_planning_question_multi_evidence_router_v1.py" $Test -Force
    } else {
        Remove-Item $Test -Force -ErrorAction SilentlyContinue
    }
    throw
}
