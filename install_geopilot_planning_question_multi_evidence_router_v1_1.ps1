$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Router="$Root\backend\app\services\data_requirement_router.py"
$PatchSource="$Root\patch_geopilot_planning_question_multi_evidence_router_v1_1.py"
$PatchTarget="$Root\backend\_patch_geopilot_planning_question_multi_evidence_router_v1_1.py"
$Test="$Root\backend\tests\test_planning_question_multi_evidence_router_v1_1.py"

foreach($P in @($Router,$PatchSource)){
    if(!(Test-Path $P)){ throw "Missing required file: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Planning Question Multi-Evidence Router V1.1"
Write-Host "Terrain + zoning/applicability composition"
Write-Host "Area + terrain + zoning -> GIS area + terrain + applicability + docs"
Write-Host "NO DB DATA UPDATE / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\planning_question_multi_evidence_router_v1_1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Router "$Backup\data_requirement_router.py"
if(Test-Path $Test){ Copy-Item $Test "$Backup\test_planning_question_multi_evidence_router_v1_1.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Preflight V1 gate"
    $r=Get-Content $Router -Raw
    if($r -notmatch 'capability="planning_multi_evidence"'){
        throw "Multi-Evidence Router V1 is not installed."
    }
    if($r -match 'mixed_tools: list\[str\]'){
        throw "V1.1 already appears installed."
    }
    Write-Host "preflight_state=CONFIRMED"

    Write-Host "[1] Stage validated patcher"
    Copy-Item $PatchSource $PatchTarget -Force

    Write-Host "[2] Patcher syntax check"
    docker compose exec -T backend python -m py_compile /app/_patch_geopilot_planning_question_multi_evidence_router_v1_1.py
    if($LASTEXITCODE-ne 0){ throw "Patcher syntax check failed." }

    Write-Host "[3] Apply router V1.1 patch"
    docker compose exec -T backend python /app/_patch_geopilot_planning_question_multi_evidence_router_v1_1.py
    if($LASTEXITCODE-ne 0){ throw "Router V1.1 patch failed." }

    Write-Host "[4] Install focused regression"
@'
from app.services.data_requirement_router import route_question


def test_zoning_only_preserves_general_applicability_route():
    r = route_question("Apakah zoning atau guna tanah yang terpakai kepada tapak ini?")
    assert r.capability == "planning_general"
    assert r.tools == ("gis.site_applicability", "documents.search")


def test_area_plus_zoning_preserves_area_applicability_documents():
    r = route_question("Apakah keluasan tapak dan zoning yang terpakai kepada tapak ini?")
    assert r.capability == "planning_general"
    assert r.tools == ("gis.site_area", "gis.site_applicability", "documents.search")


def test_terrain_plus_zoning_composes_applicability_and_documents():
    r = route_question(
        "Apakah terrain termasuk elevation dan slope serta zoning yang terpakai kepada tapak ini?"
    )
    assert r.capability == "planning_multi_evidence"
    assert r.tools == (
        "terrain.site_summary",
        "gis.site_applicability",
        "documents.search",
    )


def test_area_terrain_zoning_composes_all_supported_tools():
    r = route_question(
        "Apakah keluasan tapak, terrain termasuk elevation dan slope, "
        "serta zoning, guna tanah atau planning area yang terpakai kepada tapak ini?"
    )
    assert r.capability == "planning_multi_evidence"
    assert r.tools == (
        "gis.site_area",
        "terrain.site_summary",
        "gis.site_applicability",
        "documents.search",
    )


def test_area_plus_terrain_without_zoning_remains_two_tool_route():
    r = route_question(
        "Apakah keluasan tapak dan keadaan terrain termasuk elevation dan slope?"
    )
    assert r.capability == "planning_multi_evidence"
    assert r.tools == ("gis.site_area", "terrain.site_summary")


def test_pure_terrain_remains_direct():
    r = route_question("Berapakah slope maksimum dan elevation purata?")
    assert r.capability == "terrain_measurement"
    assert r.tools == ("terrain.site_summary",)


def test_terrain_policy_precedence_remains_document_only():
    r = route_question("Apakah garis panduan pembangunan cerun dan slope yang terpakai?")
    assert r.capability == "terrain_policy"
    assert r.tools == ("documents.search",)
'@ | Set-Content $Test -Encoding UTF8

    Write-Host "[5] Backend syntax checks"
    docker compose exec -T backend python -m py_compile app/services/data_requirement_router.py tests/test_planning_question_multi_evidence_router_v1_1.py
    if($LASTEXITCODE-ne 0){ throw "Backend syntax check failed." }

    Write-Host "[6] Focused V1.1 regressions"
    docker compose exec -T backend python -m pytest -q tests/test_planning_question_multi_evidence_router_v1_1.py
    if($LASTEXITCODE-ne 0){ throw "Focused V1.1 regression failed." }

    Write-Host "[7] Preserve V1 + lifecycle/evidence regressions"
    foreach($Regression in @(
        "tests/test_planning_question_multi_evidence_router_v1.py",
        "tests/test_track_b_planning_evidence_lifecycle_bridge_v2_3.py",
        "tests/test_auto_research_evidence_scope_bridge_v2.py",
        "tests/test_track_b_hackathon.py"
    )){
        if(Test-Path "$Root\backend\$Regression"){
            docker compose exec -T backend python -m pytest -q $Regression
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $Regression" }
        }
    }

    Write-Host "[8] Runtime composition verification"
    docker compose exec -T backend python -c "from app.services.data_requirement_router import route_question; tests=['Apakah zoning atau guna tanah yang terpakai kepada tapak ini?','Apakah keluasan tapak dan zoning yang terpakai kepada tapak ini?','Apakah terrain termasuk elevation dan slope serta zoning yang terpakai kepada tapak ini?','Apakah keluasan tapak, terrain termasuk elevation dan slope, serta zoning, guna tanah atau planning area yang terpakai kepada tapak ini?']; [(print(q),print(route_question(q).capability),print(route_question(q).tools),print()) for q in tests]"
    if($LASTEXITCODE-ne 0){ throw "Runtime composition verification failed." }

    Write-Host "[9] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5
    Write-Host "[10] Backend health"
    docker compose ps backend

    Remove-Item $PatchTarget -Force -ErrorAction SilentlyContinue

    Write-Host "============================================================"
    Write-Host "PLANNING QUESTION MULTI-EVIDENCE ROUTER V1.1 PASS"
    Write-Host "============================================================"
    Write-Host "Terrain + zoning composition: ENABLED"
    Write-Host "Area + terrain + zoning composition: ENABLED"
    Write-Host "gis.site_applicability: INCLUDED WHEN REQUESTED"
    Write-Host "documents.search: INCLUDED WITH APPLICABILITY INTENT"
    Write-Host "Area + terrain only behavior: PRESERVED"
    Write-Host "Pure terrain direct route: PRESERVED"
    Write-Host "Terrain policy precedence: PRESERVED"
    Write-Host "Lifecycle AVAILABLE bridge: PRESERVED"
    Write-Host "Evidence scope bridge: PRESERVED"
    Write-Host "DB flags changed: NONE"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend change: NONE"
    Write-Host "Next gate: RETEST AREA + TERRAIN + ZONING QUESTION"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring router/test backup."
    Copy-Item "$Backup\data_requirement_router.py" $Router -Force
    Remove-Item $PatchTarget -Force -ErrorAction SilentlyContinue

    if(Test-Path "$Backup\test_planning_question_multi_evidence_router_v1_1.py"){
        Copy-Item "$Backup\test_planning_question_multi_evidence_router_v1_1.py" $Test -Force
    } else {
        Remove-Item $Test -Force -ErrorAction SilentlyContinue
    }
    throw
}
