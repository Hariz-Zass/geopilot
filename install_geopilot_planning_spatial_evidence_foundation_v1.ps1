$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest

$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$ServiceSource="$Root\planning_spatial_evidence_service_v1.py"
$TestSource="$Root\planning_spatial_evidence_test_v1.py"
$PatcherSource="$Root\patch_geopilot_planning_spatial_evidence_foundation_v1.py"

$ServiceTarget="$Root\backend\app\services\planning_spatial_evidence.py"
$TestTarget="$Root\backend\tests\test_planning_spatial_evidence_foundation_v1.py"

foreach($P in @($ServiceSource,$TestSource,$PatcherSource)){
    if(!(Test-Path $P)){ throw "Missing required installer component: $P" }
}

Write-Host "============================================================"
Write-Host "GeoPilot Planning Spatial Evidence Foundation V1"
Write-Host "Controlled planning Polygon/MultiPolygon ingestion"
Write-Host "Reuse GISLayer + GISFeature services"
Write-Host "NO DB DATA IMPORT / NO MIGRATION / NO FRONTEND CHANGE"
Write-Host "============================================================"

$Stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$Backup="$Root\artifacts\planning_spatial_evidence_foundation_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
if(Test-Path $ServiceTarget){ Copy-Item $ServiceTarget "$Backup\planning_spatial_evidence.py" }
if(Test-Path $TestTarget){ Copy-Item $TestTarget "$Backup\test_planning_spatial_evidence_foundation_v1.py" }
Write-Host "BACKUP: $Backup"

try {
    Write-Host "[0] Preflight"
    if(Test-Path $ServiceTarget){
        throw "planning_spatial_evidence.py already exists; stop for manual audit."
    }

    $Applic="$Root\backend\app\services\site_applicability.py"
    $Layers="$Root\backend\app\services\gis_layers.py"
    $Features="$Root\backend\app\services\gis_features.py"

    foreach($P in @($Applic,$Layers,$Features)){
        if(!(Test-Path $P)){ throw "Required existing GIS service missing: $P" }
    }

    $a=Get-Content $Applic -Raw
    if($a -notmatch '"planning_block"' -or
       $a -notmatch '"planning_subzone"' -or
       $a -notmatch '"zoning"' -or
       $a -notmatch '"land_use"'){
        throw "Existing applicability-role contract differs from expected V1 roles."
    }
    Write-Host "preflight_state=CONFIRMED"

    Write-Host "[1] Stage installer components inside backend mount"
    Copy-Item $ServiceSource "$Root\backend\_planning_spatial_evidence_service.py" -Force
    Copy-Item $TestSource "$Root\backend\_planning_spatial_evidence_test.py" -Force
    Copy-Item $PatcherSource "$Root\backend\_patch_geopilot_planning_spatial_evidence_foundation_v1.py" -Force

    Write-Host "[2] Component syntax checks"
    docker compose exec -T backend python -m py_compile /app/_planning_spatial_evidence_service.py /app/_planning_spatial_evidence_test.py /app/_patch_geopilot_planning_spatial_evidence_foundation_v1.py
    if($LASTEXITCODE-ne 0){ throw "Installer component syntax check failed." }

    Write-Host "[3] Create foundation service + tests"
    docker compose exec -T backend python /app/_patch_geopilot_planning_spatial_evidence_foundation_v1.py
    if($LASTEXITCODE-ne 0){ throw "Foundation file creation failed." }

    Write-Host "[4] Backend syntax check"
    docker compose exec -T backend python -m py_compile app/services/planning_spatial_evidence.py tests/test_planning_spatial_evidence_foundation_v1.py
    if($LASTEXITCODE-ne 0){ throw "Foundation syntax check failed." }

    Write-Host "[5] Focused foundation regression"
    docker compose exec -T backend python -m pytest -q tests/test_planning_spatial_evidence_foundation_v1.py
    if($LASTEXITCODE-ne 0){ throw "Focused foundation regression failed." }

    Write-Host "[6] Preserve applicability / lifecycle / router regressions"
    foreach($Regression in @(
        "tests/test_track_b_planning_evidence_lifecycle_bridge_v2_3.py",
        "tests/test_planning_question_multi_evidence_router_v1.py",
        "tests/test_planning_question_multi_evidence_router_v1_2.py",
        "tests/test_auto_research_evidence_scope_bridge_v2.py"
    )){
        if(Test-Path "$Root\backend\$Regression"){
            docker compose exec -T backend python -m pytest -q $Regression
            if($LASTEXITCODE-ne 0){ throw "Regression failed: $Regression" }
        }
    }

    Write-Host "[7] Static contract verification"
    $s=Get-Content $ServiceTarget -Raw
    foreach($Required in @(
        '"zoning"',
        '"land_use"',
        '"planning_block"',
        '"planning_subzone"',
        'create_gis_layer',
        'ingest_feature_collection',
        'EPSG:4326',
        'source_status'
    )){
        if($s -notmatch [regex]::Escape($Required)){
            throw "Foundation contract missing: $Required"
        }
    }
    Write-Host "foundation_contract=PASS"

    Write-Host "[8] Recreate backend"
    docker compose up -d --no-deps --force-recreate backend
    if($LASTEXITCODE-ne 0){ throw "Backend recreate failed." }

    Start-Sleep -Seconds 5
    Write-Host "[9] Backend health"
    docker compose ps backend

    Write-Host "[10] Runtime import verification"
    docker compose exec -T backend python -c "from app.services.planning_spatial_evidence import PlanningSpatialEvidenceImportRequest, import_planning_spatial_evidence; print('runtime_planning_spatial_foundation=PASS')"
    if($LASTEXITCODE-ne 0){ throw "Runtime import verification failed." }

    Remove-Item "$Root\backend\_planning_spatial_evidence_service.py" -Force -ErrorAction SilentlyContinue
    Remove-Item "$Root\backend\_planning_spatial_evidence_test.py" -Force -ErrorAction SilentlyContinue
    Remove-Item "$Root\backend\_patch_geopilot_planning_spatial_evidence_foundation_v1.py" -Force -ErrorAction SilentlyContinue

    Write-Host "============================================================"
    Write-Host "PLANNING SPATIAL EVIDENCE FOUNDATION V1 PASS"
    Write-Host "============================================================"
    Write-Host "Controlled GeoJSON FeatureCollection: SUPPORTED"
    Write-Host "Polygon/MultiPolygon only: ENFORCED"
    Write-Host "EPSG:4326 V1 contract: ENFORCED"
    Write-Host "zoning / land_use / planning_block / planning_subzone: SUPPORTED"
    Write-Host "Existing create_gis_layer service: REUSED"
    Write-Host "Existing ingest_feature_collection service: REUSED"
    Write-Host "Source checksum + provenance: RECORDED"
    Write-Host "Automatic zoning inference from layer name: NOT ADDED"
    Write-Host "Installer DB data import: NONE"
    Write-Host "DB schema change: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Frontend change: NONE"
    Write-Host "Next gate: CONTROLLED SHAH ALAM PLANNING GEOJSON IMPORT"
    Write-Host "============================================================"
}
catch {
    Write-Host "INSTALL FAILED - restoring foundation files."
    Remove-Item "$Root\backend\_planning_spatial_evidence_service.py" -Force -ErrorAction SilentlyContinue
    Remove-Item "$Root\backend\_planning_spatial_evidence_test.py" -Force -ErrorAction SilentlyContinue
    Remove-Item "$Root\backend\_patch_geopilot_planning_spatial_evidence_foundation_v1.py" -Force -ErrorAction SilentlyContinue

    if(Test-Path "$Backup\planning_spatial_evidence.py"){
        Copy-Item "$Backup\planning_spatial_evidence.py" $ServiceTarget -Force
    } else {
        Remove-Item $ServiceTarget -Force -ErrorAction SilentlyContinue
    }

    if(Test-Path "$Backup\test_planning_spatial_evidence_foundation_v1.py"){
        Copy-Item "$Backup\test_planning_spatial_evidence_foundation_v1.py" $TestTarget -Force
    } else {
        Remove-Item $TestTarget -Force -ErrorAction SilentlyContinue
    }

    throw
}
