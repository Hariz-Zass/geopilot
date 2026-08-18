$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer GIS Bundle Recognition V1.3"
Write-Host "MapInfo + ESRI Shapefile logical bundle recognition"
Write-Host "NO DB WRITE / NO MIGRATION / INSPECTION ONLY"
Write-Host "============================================================"

$root = (Get-Location).Path
$target = Join-Path $root "backend\app\services\track_b_smart_intake.py"
$testTarget = Join-Path $root "backend\tests\test_track_b_smart_organizer_gis_bundle_v1_3.py"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $root "artifacts\smart_organizer_gis_bundle_v1_3_backup_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null

if (!(Test-Path $target)) { throw "Target not found: $target" }

Copy-Item $target (Join-Path $backup "track_b_smart_intake.py") -Force
if (Test-Path $testTarget) {
    Copy-Item $testTarget (Join-Path $backup "test_track_b_smart_organizer_gis_bundle_v1_3.py") -Force
}

Write-Host "BACKUP: $backup"

try {
    Write-Host "[1] Patch GIS bundle recognition"

    $text = Get-Content $target -Raw

    if ($text -match "SMART_ORGANIZER_GIS_BUNDLE_V1_3") {
        Write-Host "V1.3 marker already present - source patch skipped."
    }
    else {
        $oldSuffix = '_ZIP_SUPPORTED_SUFFIXES = {".tif", ".tiff", ".jp2", ".zip", ".geojson", ".json", ".pdf", ".csv"}'
        $newSuffix = '_ZIP_SUPPORTED_SUFFIXES = {".tif", ".tiff", ".jp2", ".zip", ".geojson", ".json", ".pdf", ".csv", ".tab", ".dat", ".map", ".id", ".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix"}'

        if (-not $text.Contains($oldSuffix)) {
            throw "Expected V1.2.2 suffix anchor not found. STOP - source differs from audited preflight."
        }
        $text = $text.Replace($oldSuffix, $newSuffix)

        $anchor = @'
    counts = {}
    for item in expanded:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
'@

        $replacement = @'
    # SMART_ORGANIZER_GIS_BUNDLE_V1_3
    # Recognize multi-file vector datasets as ONE logical organizer dataset.
    # This phase is inspect-only: it does not parse geometry, transform CRS,
    # create GIS layers/features, or write to the database.
    _mapinfo_required = {".tab", ".dat", ".map", ".id"}
    _shapefile_required = {".shp", ".shx", ".dbf"}
    _shapefile_optional = {".prj", ".cpg", ".qix"}
    _gis_sidecars = _mapinfo_required | _shapefile_required | _shapefile_optional

    def _bundle_key(item):
        archive_path = (item.get("archive_path") or item.get("filename") or "").replace("\\", "/")
        p = Path(archive_path)
        parent = str(p.parent).casefold()
        stem = p.stem.casefold()
        source_archive = (item.get("source_archive") or "").casefold()
        return (source_archive, parent, stem)

    bundle_members = {}
    for item in expanded:
        suffix = (item.get("extension") or "").casefold()
        if suffix in _gis_sidecars:
            bundle_members.setdefault(_bundle_key(item), []).append(item)

    gis_bundles = []
    for key, members in bundle_members.items():
        suffixes = {(x.get("extension") or "").casefold() for x in members}
        member_names = [x.get("archive_path") or x.get("filename") for x in members]

        if ".tab" in suffixes or bool(suffixes & {".dat", ".map", ".id"}):
            fmt = "mapinfo_tab"
            required = _mapinfo_required
            classification = "gis_mapinfo_bundle_candidate"
        else:
            fmt = "esri_shapefile"
            required = _shapefile_required
            classification = "gis_shapefile_bundle_candidate"

        missing = sorted(required - suffixes)
        complete = not missing
        primary_suffix = ".tab" if fmt == "mapinfo_tab" else ".shp"
        primary = next((x for x in members if (x.get("extension") or "").casefold() == primary_suffix), members[0])

        for item in members:
            item["classification"] = classification if complete else "gis_bundle_incomplete"
            item["confidence"] = "high"
            item["requires_confirmation"] = True
            item["metadata"] = {
                **(item.get("metadata") or {}),
                "logical_gis_bundle": True,
                "gis_format": fmt,
                "bundle_complete": complete,
                "bundle_members": member_names,
                "missing_required_extensions": missing,
                "primary_member": primary.get("archive_path") or primary.get("filename"),
                "geometry_not_parsed": True,
                "database_writes": False,
            }
            item["issues"] = [
                (
                    f"Recognized complete {fmt} GIS bundle. Confirm layer role, CRS and Site/project assignment before import."
                    if complete
                    else f"Incomplete {fmt} GIS bundle; missing required members: {', '.join(missing)}."
                )
            ]

        gis_bundles.append({
            "format": fmt,
            "classification": classification if complete else "gis_bundle_incomplete",
            "complete": complete,
            "members": member_names,
            "missing_required_extensions": missing,
            "primary_member": primary.get("archive_path") or primary.get("filename"),
            "requires_confirmation": True,
        })

    counts = {}
    for item in expanded:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1
'@

        if (-not $text.Contains($anchor)) {
            throw "Expected V1.2.2 counts anchor not found. STOP - source differs from audited preflight."
        }
        $text = $text.Replace($anchor, $replacement)

        $returnAnchor = @'
        "archive_expansion": True,
    }
'@
        $returnReplacement = @'
        "archive_expansion": True,
        "gis_bundle_recognition": True,
        "gis_bundle_count": len(gis_bundles),
        "gis_bundles": gis_bundles,
    }
'@
        if (-not $text.Contains($returnAnchor)) {
            throw "Expected V1.2.2 return anchor not found. STOP - source differs from audited preflight."
        }
        $text = $text.Replace($returnAnchor, $returnReplacement)

        Set-Content $target $text -Encoding UTF8
    }

    Write-Host "[2] Install focused V1.3 tests"

    $tests = @'
import io
import zipfile

import pytest
from fastapi import UploadFile

from app.services.track_b_smart_intake import inspect_organizer_package


def _zip_upload(name, members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for member_name, data in members.items():
            z.writestr(member_name, data)
    buf.seek(0)
    return UploadFile(filename=name, file=buf)


@pytest.mark.anyio
async def test_mapinfo_bundle_recognized():
    upload = _zip_upload("organizer.zip", {
        "urban/T1/Ndcdb_lot.TAB": b"tab",
        "urban/T1/Ndcdb_lot.DAT": b"dat",
        "urban/T1/Ndcdb_lot.MAP": b"map",
        "urban/T1/Ndcdb_lot.ID": b"id",
    })
    result = await inspect_organizer_package([upload])
    assert result["database_writes"] is False
    assert result["gis_bundle_recognition"] is True
    assert result["gis_bundle_count"] == 1
    bundle = result["gis_bundles"][0]
    assert bundle["format"] == "mapinfo_tab"
    assert bundle["complete"] is True
    assert bundle["missing_required_extensions"] == []
    assert all(
        x["classification"] == "gis_mapinfo_bundle_candidate"
        for x in result["items"]
    )


@pytest.mark.anyio
async def test_shapefile_bundle_recognized():
    upload = _zip_upload("organizer.zip", {
        "rural/T2/parcel.shp": b"shp",
        "rural/T2/parcel.shx": b"shx",
        "rural/T2/parcel.dbf": b"dbf",
        "rural/T2/parcel.prj": b"prj",
    })
    result = await inspect_organizer_package([upload])
    assert result["gis_bundle_count"] == 1
    bundle = result["gis_bundles"][0]
    assert bundle["format"] == "esri_shapefile"
    assert bundle["complete"] is True


@pytest.mark.anyio
async def test_incomplete_mapinfo_bundle_requires_confirmation():
    upload = _zip_upload("organizer.zip", {
        "urban/T1/broken.TAB": b"tab",
        "urban/T1/broken.DAT": b"dat",
    })
    result = await inspect_organizer_package([upload])
    assert result["gis_bundle_count"] == 1
    bundle = result["gis_bundles"][0]
    assert bundle["complete"] is False
    assert ".map" in bundle["missing_required_extensions"]
    assert ".id" in bundle["missing_required_extensions"]
    assert all(
        x["classification"] == "gis_bundle_incomplete"
        for x in result["items"]
    )


@pytest.mark.anyio
async def test_same_stem_different_folders_not_merged():
    upload = _zip_upload("organizer.zip", {
        "urban/T1/parcel.shp": b"a",
        "urban/T1/parcel.shx": b"a",
        "urban/T1/parcel.dbf": b"a",
        "rural/T2/parcel.shp": b"b",
        "rural/T2/parcel.shx": b"b",
        "rural/T2/parcel.dbf": b"b",
    })
    result = await inspect_organizer_package([upload])
    assert result["gis_bundle_count"] == 2
    assert all(x["complete"] for x in result["gis_bundles"])
'@
    Set-Content $testTarget $tests -Encoding UTF8

    Write-Host "[3] Recreate backend so runtime sees source"
    docker compose up -d --force-recreate backend
    if ($LASTEXITCODE -ne 0) { throw "Backend recreate failed." }

    Start-Sleep -Seconds 8
    docker compose ps backend

    Write-Host "[4] Python syntax"
    docker compose exec -T backend python -m py_compile /app/app/services/track_b_smart_intake.py
    if ($LASTEXITCODE -ne 0) { throw "Python syntax check failed." }

    Write-Host "[5] V1.3 focused tests"
    docker compose exec -T backend python -m pytest -q tests/test_track_b_smart_organizer_gis_bundle_v1_3.py
    if ($LASTEXITCODE -ne 0) { throw "V1.3 GIS bundle regression failed." }

    Write-Host "[6] Preserve V1.1 + V1.2.2 regressions"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_organizer_intake_v1.py `
        tests/test_track_b_smart_organizer_zip_v1_2_2.py
    if ($LASTEXITCODE -ne 0) { throw "Existing Smart Organizer regression failed." }

    Write-Host "[7] Runtime marker"
    docker compose exec -T backend python -c "from pathlib import Path; t=Path('/app/app/services/track_b_smart_intake.py').read_text(); assert 'SMART_ORGANIZER_GIS_BUNDLE_V1_3' in t; print('runtime_gis_bundle_v1_3=PASS')"
    if ($LASTEXITCODE -ne 0) { throw "Runtime marker verification failed." }

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "SMART ORGANIZER GIS BUNDLE V1.3 PASS"
    Write-Host "============================================================"
    Write-Host "MapInfo TAB/DAT/MAP/ID grouping: ENABLED"
    Write-Host "ESRI SHP/SHX/DBF (+ PRJ/CPG/QIX) grouping: ENABLED"
    Write-Host "Bundle completeness validation: ENABLED"
    Write-Host "Geometry parsing/conversion: NOT YET"
    Write-Host "Database writes: NONE"
    Write-Host "Migration: NONE"
    Write-Host "Next gate: LIVE ORGANIZER ZIP GIS BUNDLE INSPECTION"
}
catch {
    Write-Host ""
    Write-Host "INSTALL FAILED - restoring backup."

    Copy-Item (Join-Path $backup "track_b_smart_intake.py") $target -Force

    $oldTest = Join-Path $backup "test_track_b_smart_organizer_gis_bundle_v1_3.py"
    if (Test-Path $oldTest) {
        Copy-Item $oldTest $testTarget -Force
    }
    elseif (Test-Path $testTarget) {
        Remove-Item $testTarget -Force
    }

    docker compose up -d --force-recreate backend | Out-Host
    throw
}
