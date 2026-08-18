$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = Join-Path $Root "artifacts\terrain_userflow_integration_v1_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null

Copy-Item "backend\app\services\terrain_analysis.py" $Backup
Copy-Item "backend\app\api\v1\terrain.py" $Backup
Copy-Item "backend\tests\test_terrain_analysis.py" $Backup

Write-Host "============================================================"
Write-Host "GeoPilot Terrain Normal User Flow Integration V1"
Write-Host "============================================================"
Write-Host "BACKUP: $Backup"

$Patch = @'
from pathlib import Path
analysis=Path("/app/app/services/terrain_analysis.py")
api=Path("/app/app/api/v1/terrain.py")
test=Path("/app/tests/test_terrain_analysis.py")

s=analysis.read_text(encoding="utf-8-sig")
old="from app.services.terrain_acquisition import preferred_site_dem, TerrainAcquisitionError"
new="from app.services.terrain_acquisition import (\n    acquire_site_dem_if_missing,\n    preferred_site_dem,\n    TerrainAcquisitionError,\n)"
assert old in s, "terrain_analysis import marker missing"
s=s.replace(old,new,1)

old='''    if dataset is None:
        raise TerrainEvidenceMissing(
            "No ready project/site-scoped DEM or elevation raster is available."
        )
'''
new='''    if dataset is None:
        try:
            dataset = acquire_site_dem_if_missing(
                session,
                owner=owner,
                project_id=project_id,
                site_id=site_id,
            )
        except TerrainAcquisitionError as exc:
            raise TerrainEvidenceMissing(str(exc)) from exc
'''
assert old in s, "missing-DEM branch marker missing"
s=s.replace(old,new,1)
analysis.write_text(s,encoding="utf-8")

a=api.read_text(encoding="utf-8-sig")
old="from app.schemas.raster import RasterDatasetResponse\nfrom app.services.terrain_ingestion import ingest_site_dem"
new="from app.schemas.raster import RasterDatasetResponse\nfrom app.services.terrain_ingestion import ingest_site_dem\nfrom app.services.terrain_analysis import TerrainAnalysisError, TerrainEvidenceMissing, calculate_site_terrain_summary"
assert old in a, "terrain API import marker missing"
a=a.replace(old,new,1)
assert '@router.post("/analysis")' not in a, "analysis endpoint already exists"
a += '''

@router.post("/analysis")
def analyze_terrain(
    project_id: uuid.UUID,
    site_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        summary = calculate_site_terrain_summary(
            session,
            owner=current_user,
            project_id=project_id,
            site_id=site_id,
        )
        return {
            "raster_id": str(summary.raster_id),
            "raster_checksum_sha256": summary.raster_checksum_sha256,
            "source_uri": summary.source_uri,
            "crs": summary.crs,
            "valid_pixel_count": summary.valid_pixel_count,
            "elevation_min_m": summary.elevation_min_m,
            "elevation_max_m": summary.elevation_max_m,
            "elevation_mean_m": summary.elevation_mean_m,
            "slope_min_degrees": summary.slope_min_degrees,
            "slope_max_degrees": summary.slope_max_degrees,
            "slope_mean_degrees": summary.slope_mean_degrees,
            "max_slope_longitude": summary.max_slope_longitude,
            "max_slope_latitude": summary.max_slope_latitude,
        }
    except (TerrainEvidenceMissing, TerrainAnalysisError) as exc:
        session.rollback()
        raise _error(exc) from exc
    except Exception as exc:
        session.rollback()
        raise _error(exc) from exc
'''
api.write_text(a,encoding="utf-8")

t=test.read_text(encoding="utf-8-sig")
if "test_select_site_dem_auto_acquires_only_when_missing" not in t:
    t += '''

def test_select_site_dem_auto_acquires_only_when_missing(monkeypatch):
    from app.services import terrain_analysis
    sentinel = SimpleNamespace(source_uri="local://rasters/auto.tif")
    calls = {"preferred": 0, "acquire": 0}
    monkeypatch.setattr(terrain_analysis, "resolve_project_scope", lambda *a, **k: None)
    monkeypatch.setattr(terrain_analysis, "resolve_site_scope", lambda *a, **k: None)
    def preferred(*args, **kwargs):
        calls["preferred"] += 1
        return None
    def acquire(*args, **kwargs):
        calls["acquire"] += 1
        return sentinel
    monkeypatch.setattr(terrain_analysis, "preferred_site_dem", preferred)
    monkeypatch.setattr(terrain_analysis, "acquire_site_dem_if_missing", acquire)
    result = terrain_analysis.select_site_dem(object(), owner=object(), project_id=uuid.uuid4(), site_id=uuid.uuid4())
    assert result is sentinel
    assert calls == {"preferred": 1, "acquire": 1}


def test_select_site_dem_preserves_existing_dem_precedence(monkeypatch):
    from app.services import terrain_analysis
    manual = SimpleNamespace(source_uri="local://rasters/manual.tif")
    calls = {"acquire": 0}
    monkeypatch.setattr(terrain_analysis, "resolve_project_scope", lambda *a, **k: None)
    monkeypatch.setattr(terrain_analysis, "resolve_site_scope", lambda *a, **k: None)
    monkeypatch.setattr(terrain_analysis, "preferred_site_dem", lambda *a, **k: manual)
    def acquire(*args, **kwargs):
        calls["acquire"] += 1
        raise AssertionError("auto acquisition must not run when a ready DEM exists")
    monkeypatch.setattr(terrain_analysis, "acquire_site_dem_if_missing", acquire)
    result = terrain_analysis.select_site_dem(object(), owner=object(), project_id=uuid.uuid4(), site_id=uuid.uuid4())
    assert result is manual
    assert calls["acquire"] == 0
'''
test.write_text(t,encoding="utf-8")
print("PATCH APPLIED")
'@

Write-Host "`n[1] Apply minimal backend integration patch"
$Patch | docker compose exec -T backend python -
if ($LASTEXITCODE -ne 0) { throw "Patch failed." }

Write-Host "`n[2] Syntax checks"
docker compose exec -T backend python -m py_compile app/services/terrain_analysis.py app/api/v1/terrain.py tests/test_terrain_analysis.py
if ($LASTEXITCODE -ne 0) { throw "Syntax check failed." }

Write-Host "`n[3] Terrain regression tests"
docker compose exec -T backend python -m pytest -q tests/test_terrain_analysis.py tests/test_terrain_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Terrain regression tests failed." }

Write-Host "`n[4] Verify route registration"
docker compose exec -T backend python -c "from app.main import app; rows=[(r.path,r.methods) for r in app.routes if '/terrain' in r.path]; [print(r) for r in rows]; assert any(p.endswith('/terrain/analysis') and 'POST' in m for p,m in rows)"
if ($LASTEXITCODE -ne 0) { throw "Route registration failed." }

Write-Host "`n[5] Service health"
docker compose ps
if ($LASTEXITCODE -ne 0) { throw "Service health check failed." }

Write-Host "`n============================================================"
Write-Host "TERRAIN NORMAL USER FLOW INTEGRATION V1 PASS"
Write-Host "============================================================"
Write-Host "Existing/manual DEM precedence: PRESERVED"
Write-Host "Missing DEM auto acquisition: WIRED"
Write-Host "Terrain analysis endpoint: POST .../terrain/analysis"
Write-Host "Frontend changed: NO"
Write-Host "Migration: NONE"
Write-Host "Existing DB rows modified by installer: NO"
Write-Host "============================================================"
