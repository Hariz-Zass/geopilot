$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer Format Coverage V1.3.3"
Write-Host "Repair after V1.3.2 runtime-verification quoting failure"
Write-Host "GPKG candidate + MapInfo IND optional sidecar + QMD auxiliary"
Write-Host "NO DB WRITE / NO MIGRATION"
Write-Host "============================================================"

$root = (Get-Location).Path
$target = Join-Path $root "backend\app\services\track_b_smart_intake.py"
$test = Join-Path $root "backend\tests\test_track_b_smart_organizer_format_coverage_v1_3_3.py"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "artifacts\smart_organizer_format_coverage_v1_3_3_backup_$stamp"

if (-not (Test-Path $target)) { throw "Missing target: $target" }

New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $target (Join-Path $backup "track_b_smart_intake.py") -Force
if (Test-Path $test) {
    Copy-Item $test (Join-Path $backup "test_track_b_smart_organizer_format_coverage_v1_3_3.py") -Force
}
Write-Host "BACKUP: $backup"

function Restore-Backup {
    Copy-Item (Join-Path $backup "track_b_smart_intake.py") $target -Force
    $old = Join-Path $backup "test_track_b_smart_organizer_format_coverage_v1_3_3.py"
    if (Test-Path $old) {
        Copy-Item $old $test -Force
    } elseif (Test-Path $test) {
        Remove-Item $test -Force
    }
}

try {
    Write-Host "[0] Confirm clean V1.3 rollback baseline"
    $src = Get-Content $target -Raw

    foreach ($needle in @(
        "SMART_ORGANIZER_ZIP_V1_2_2",
        "SMART_ORGANIZER_GIS_BUNDLE_V1_3",
        '_mapinfo_required = {".tab", ".dat", ".map", ".id"}',
        '"gis_bundles": gis_bundles'
    )) {
        if (-not $src.Contains($needle)) {
            throw "Expected V1.3 source marker missing: $needle"
        }
    }

    if ($src.Contains("SMART_ORGANIZER_FORMAT_COVERAGE_V1_3_3")) {
        throw "V1.3.3 already present. Stop and inspect."
    }

    Write-Host "baseline=CONFIRMED"

    Write-Host "[1] Extend ZIP-recognized suffixes"
    $oldSuffix = '_ZIP_SUPPORTED_SUFFIXES = {".tif", ".tiff", ".jp2", ".zip", ".geojson", ".json", ".pdf", ".csv", ".tab", ".dat", ".map", ".id", ".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix"}'
    $newSuffix = '_ZIP_SUPPORTED_SUFFIXES = {".tif", ".tiff", ".jp2", ".zip", ".geojson", ".json", ".pdf", ".csv", ".tab", ".dat", ".map", ".id", ".ind", ".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".gpkg", ".qmd"}'

    if (-not $src.Contains($oldSuffix)) {
        throw "V1.3 ZIP suffix contract differs from expected rollback baseline."
    }
    $src = $src.Replace($oldSuffix, $newSuffix)

    Write-Host "[2] Add MapInfo .IND as optional sidecar"
    $oldMapInfo = @'
    _mapinfo_required = {".tab", ".dat", ".map", ".id"}
    _shapefile_required = {".shp", ".shx", ".dbf"}
    _shapefile_optional = {".prj", ".cpg", ".qix"}
    _gis_sidecars = _mapinfo_required | _shapefile_required | _shapefile_optional
'@
    $newMapInfo = @'
    _mapinfo_required = {".tab", ".dat", ".map", ".id"}
    _mapinfo_optional = {".ind"}
    _shapefile_required = {".shp", ".shx", ".dbf"}
    _shapefile_optional = {".prj", ".cpg", ".qix"}
    _gis_sidecars = _mapinfo_required | _mapinfo_optional | _shapefile_required | _shapefile_optional
'@

    if (-not $src.Contains($oldMapInfo)) {
        throw "V1.3 GIS bundle set contract differs from expected rollback baseline."
    }
    $src = $src.Replace($oldMapInfo, $newMapInfo)

    Write-Host "[3] Add GPKG/QMD classification"
    $countsAnchor = @'
    counts = {}
    for item in expanded:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
'@

    $coverageBlock = @'
    # SMART_ORGANIZER_FORMAT_COVERAGE_V1_3_3
    # Inspection-only format coverage. No GIS parsing/conversion and no DB writes.
    for item in expanded:
        suffix = (item.get("extension") or "").casefold()

        if suffix == ".gpkg":
            item["classification"] = "gis_geopackage_candidate"
            item["confidence"] = "high"
            item["requires_confirmation"] = True
            item["metadata"] = {
                **(item.get("metadata") or {}),
                "gis_format": "geopackage",
                "geometry_not_parsed": True,
                "database_writes": False,
            }
            item["issues"] = [
                "Recognized GeoPackage GIS dataset. Confirm layer role, CRS and Site/project assignment before import."
            ]

        elif suffix == ".qmd":
            item["classification"] = "organizer_auxiliary_ignored"
            item["confidence"] = "high"
            item["requires_confirmation"] = False
            item["metadata"] = {
                **(item.get("metadata") or {}),
                "auxiliary_only": True,
                "database_writes": False,
            }
            item["issues"] = [
                "Recognized auxiliary QMD member. It is safely ignored for spatial import."
            ]

    counts = {}
    for item in expanded:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
'@

    if (-not $src.Contains($countsAnchor)) {
        throw "Exact V1.3 counts anchor not found."
    }
    $src = $src.Replace($countsAnchor, $coverageBlock)

    Set-Content $target $src -Encoding UTF8

    Write-Host "[4] Install focused tests"
    @'
from pathlib import Path

def test_v133_static_contract():
    text = Path("/app/app/services/track_b_smart_intake.py").read_text()
    assert "SMART_ORGANIZER_FORMAT_COVERAGE_V1_3_3" in text
    assert '_mapinfo_optional = {".ind"}' in text
    assert "gis_geopackage_candidate" in text
    assert "organizer_auxiliary_ignored" in text

def test_ind_optional_contract():
    text = Path("/app/app/services/track_b_smart_intake.py").read_text()
    assert '_mapinfo_required = {".tab", ".dat", ".map", ".id"}' in text
    assert '_mapinfo_optional = {".ind"}' in text
'@ | Set-Content $test -Encoding UTF8

    Write-Host "[5] Python syntax"
    docker compose exec -T backend python -m py_compile /app/app/services/track_b_smart_intake.py
    if ($LASTEXITCODE -ne 0) { throw "Syntax check failed." }

    Write-Host "[6] Smart Organizer regression"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_organizer_intake_v1.py `
        tests/test_track_b_smart_organizer_zip_v1_2_2.py `
        tests/test_track_b_smart_organizer_gis_bundle_v1_3.py `
        tests/test_track_b_smart_organizer_format_coverage_v1_3_3.py
    if ($LASTEXITCODE -ne 0) { throw "Focused regression failed." }

    Write-Host "[7] Full backend regression"
    docker compose exec -T backend python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "Full backend regression failed." }

    Write-Host "[8] Recreate backend"
    docker compose up -d --force-recreate backend
    if ($LASTEXITCODE -ne 0) { throw "Backend recreate failed." }
    Start-Sleep -Seconds 8
    docker compose ps backend

    Write-Host "[9] Runtime verification"
    $verify = @'
from pathlib import Path
t = Path("/app/app/services/track_b_smart_intake.py").read_text()
assert "SMART_ORGANIZER_FORMAT_COVERAGE_V1_3_3" in t
assert '_mapinfo_optional = {".ind"}' in t
assert "gis_geopackage_candidate" in t
assert "organizer_auxiliary_ignored" in t
print("runtime_format_coverage_v1_3_3=PASS")
'@
    $verify | docker compose exec -T backend python -
    if ($LASTEXITCODE -ne 0) { throw "Runtime verification failed." }

    Write-Host "[10] DB safety"
    $dbcheck = @'
from app.db import get_session_factory
from sqlalchemy import text
with get_session_factory()() as db:
    print("alembic_revision=", db.execute(text("SELECT version_num FROM alembic_version")).scalar())
    print("gis_layers=", db.execute(text("SELECT COUNT(*) FROM gis_layers")).scalar())
    print("gis_features=", db.execute(text("SELECT COUNT(*) FROM gis_features")).scalar())
'@
    $dbcheck | docker compose exec -T backend python -
    if ($LASTEXITCODE -ne 0) { throw "DB safety check failed." }

    Write-Host "============================================================"
    Write-Host "SMART ORGANIZER FORMAT COVERAGE V1.3.3 PASS"
    Write-Host "============================================================"
    Write-Host "GeoPackage (.gpkg): GIS CANDIDATE"
    Write-Host "MapInfo .IND: OPTIONAL SIDECAR"
    Write-Host "QMD: AUXILIARY / SAFE IGNORE"
    Write-Host "Geometry parsing/conversion: NOT YET"
    Write-Host "Database writes: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Next gate: LIVE ORGANIZER ZIP FORMAT COVERAGE RETEST"
}
catch {
    Write-Host ""
    Write-Host "INSTALL FAILED - restoring V1.3 baseline."
    Restore-Backup
    docker compose up -d --force-recreate backend | Out-Host
    throw
}
