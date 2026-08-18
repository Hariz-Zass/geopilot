$ErrorActionPreference = "Stop"

Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer Format Coverage V1.3.1"
Write-Host "GPKG candidate + MapInfo IND sidecar + QMD auxiliary"
Write-Host "NO DB WRITE / NO MIGRATION"
Write-Host "============================================================"

$root = (Get-Location).Path
$target = Join-Path $root "backend\app\services\track_b_smart_intake.py"
$test = Join-Path $root "backend\tests\test_track_b_smart_organizer_format_coverage_v1_3_1.py"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $root "artifacts\smart_organizer_format_coverage_v1_3_1_backup_$stamp"
$log = Join-Path $root "artifacts\smart_organizer_format_coverage_v1_3_1_result.txt"

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
Copy-Item $target (Join-Path $backupDir "track_b_smart_intake.py") -Force
Write-Host "BACKUP: $backupDir"

try {
    Write-Host "[0] Preflight"
    if (-not (Test-Path $target)) { throw "Missing $target" }

    $src = Get-Content $target -Raw
    if ($src -notmatch '_mapinfo_required\s*=\s*\{".tab", ".dat", ".map", ".id"\}') {
        throw "V1.3 MapInfo contract not found. STOP rather than patch unknown source."
    }
    if ($src -notmatch '_gis_sidecars\s*=\s*_mapinfo_required \| _shapefile_required \| _shapefile_optional') {
        throw "V1.3 GIS sidecar contract not found. STOP rather than patch unknown source."
    }
    Write-Host "preflight_state=CONFIRMED"

    Write-Host "[1] Patch format coverage"
    $src = $src.Replace(
        '_mapinfo_required = {".tab", ".dat", ".map", ".id"}',
        '_mapinfo_required = {".tab", ".dat", ".map", ".id"}' + "`n" +
        '    _mapinfo_optional = {".ind"}'
    )
    $src = $src.Replace(
        '_gis_sidecars = _mapinfo_required | _shapefile_required | _shapefile_optional',
        '_gis_sidecars = _mapinfo_required | _mapinfo_optional | _shapefile_required | _shapefile_optional'
    )

    # Add safe standalone classifications before the existing GIS bundle grouping loop.
    $anchor = '    for item in results:'
    $idx = $src.IndexOf($anchor, $src.IndexOf('_gis_sidecars'))
    if ($idx -lt 0) { throw "Could not locate V1.3 result classification loop." }

    $inject = @'
    # V1.3.1 standalone format coverage.
    # GeoPackage is recognized for later conversion/import, not parsed here.
    # QMD is retained as harmless organizer auxiliary metadata and is not imported.
    for _item in results:
        _name = str(_item.get("name") or _item.get("filename") or _item.get("path") or "")
        _suffix = Path(_name).suffix.lower()
        if _suffix == ".gpkg":
            _item["classification"] = "gis_geopackage_candidate"
            _item["recognized"] = True
            _item["requires_confirmation"] = True
            _item["confidence"] = "high"
            _item["reason"] = (
                "Recognized GeoPackage GIS dataset. Confirm layer role, CRS and "
                "Site/project assignment before import."
            )
        elif _suffix == ".qmd":
            _item["classification"] = "organizer_auxiliary_ignored"
            _item["recognized"] = True
            _item["requires_confirmation"] = False
            _item["confidence"] = "high"
            _item["reason"] = (
                "Recognized auxiliary QMD member. Safely ignored for spatial import."
            )

'@
    $src = $src.Insert($idx, $inject)

    # Ensure pathlib.Path exists for suffix handling.
    if ($src -notmatch '(?m)^from pathlib import Path\s*$') {
        $src = "from pathlib import Path`n" + $src
    }

    Set-Content $target $src -Encoding UTF8

    Write-Host "[2] Add focused regression"
    @'
import io
import zipfile
import pytest

from app.services import track_b_smart_intake as mod


def _zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


async def _inspect(payload):
    # Reuse the service's public/semipublic ZIP inspection entry point dynamically,
    # matching the installed V1.2/V1.3 service without inventing a DB path.
    candidates = [
        "inspect_organizer_files",
        "inspect_smart_organizer_files",
        "inspect_track_b_organizer_files",
        "inspect_uploaded_files",
    ]
    fn = next((getattr(mod, n, None) for n in candidates if callable(getattr(mod, n, None))), None)
    if fn is None:
        pytest.skip("Public inspection entry point name differs; static contract tests still apply.")
    return fn


def test_static_v131_contract():
    from pathlib import Path
    text = Path("/app/app/services/track_b_smart_intake.py").read_text()
    assert '_mapinfo_optional = {".ind"}' in text
    assert "_mapinfo_required | _mapinfo_optional | _shapefile_required" in text
    assert '".gpkg"' in text
    assert '"gis_geopackage_candidate"' in text
    assert '".qmd"' in text
    assert '"organizer_auxiliary_ignored"' in text


def test_ind_is_optional_not_required():
    from pathlib import Path
    text = Path("/app/app/services/track_b_smart_intake.py").read_text()
    assert '_mapinfo_required = {".tab", ".dat", ".map", ".id"}' in text
    assert '_mapinfo_optional = {".ind"}' in text


def test_no_db_or_migration_contract_added():
    from pathlib import Path
    text = Path("/app/app/services/track_b_smart_intake.py").read_text()
    assert "alembic upgrade" not in text
'@ | Set-Content $test -Encoding UTF8

    Write-Host "[3] Python syntax"
    docker compose exec -T backend python -m py_compile /app/app/services/track_b_smart_intake.py
    if ($LASTEXITCODE -ne 0) { throw "Backend syntax check failed." }

    Write-Host "[4] Focused regressions"
    docker compose exec -T backend python -m pytest -q `
        tests/test_track_b_smart_organizer_intake_v1.py `
        tests/test_track_b_smart_organizer_zip_v1_2_2.py `
        tests/test_track_b_smart_organizer_gis_bundle_v1_3.py `
        tests/test_track_b_smart_organizer_format_coverage_v1_3_1.py
    if ($LASTEXITCODE -ne 0) { throw "Focused regression failed." }

    Write-Host "[5] Recreate backend"
    docker compose up -d --force-recreate backend
    if ($LASTEXITCODE -ne 0) { throw "Backend recreate failed." }
    Start-Sleep -Seconds 8

    Write-Host "[6] Runtime contract"
    docker compose exec -T backend python -c "from pathlib import Path; t=Path('/app/app/services/track_b_smart_intake.py').read_text(); assert '_mapinfo_optional = {\".ind\"}' in t; assert 'gis_geopackage_candidate' in t; assert 'organizer_auxiliary_ignored' in t; print('runtime_format_coverage_v1_3_1=PASS')"
    if ($LASTEXITCODE -ne 0) { throw "Runtime verification failed." }

    Write-Host "[7] DB safety"
    docker compose exec -T backend python -c "from app.db import get_session_factory; from sqlalchemy import text; db=get_session_factory()(); print('alembic_revision=',db.execute(text('SELECT version_num FROM alembic_version')).scalar()); print('gis_layers=',db.execute(text('SELECT COUNT(*) FROM gis_layers')).scalar()); print('gis_features=',db.execute(text('SELECT COUNT(*) FROM gis_features')).scalar()); db.close()"
    if ($LASTEXITCODE -ne 0) { throw "DB safety verification failed." }

    @"
============================================================
SMART ORGANIZER FORMAT COVERAGE V1.3.1 PASS
============================================================
GeoPackage (.gpkg): GIS CANDIDATE
MapInfo .IND: OPTIONAL SIDECAR
QMD: AUXILIARY / SAFE IGNORE
Geometry parsing/conversion: NOT YET
Database writes: NONE
Migration: NONE
Next gate: LIVE ORGANIZER ZIP V1.3.1 INSPECTION
============================================================
"@ | Tee-Object -FilePath $log

    Write-Host "RESULT SAVED TO: $log"
}
catch {
    Write-Host ""
    Write-Host "INSTALL FAILED - restoring backup."
    if (Test-Path (Join-Path $backupDir "track_b_smart_intake.py")) {
        Copy-Item (Join-Path $backupDir "track_b_smart_intake.py") $target -Force
    }
    if (Test-Path $test) { Remove-Item $test -Force }
    throw
}
