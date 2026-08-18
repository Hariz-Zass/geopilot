
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$out = ".\geopilot_dem_ingestion_audit.txt"
if (Test-Path $out) { Remove-Item $out -Force }

function Add-Section([string]$title, [string]$content) {
  Add-Content -Path $out -Value ""
  Add-Content -Path $out -Value ("=" * 90)
  Add-Content -Path $out -Value $title
  Add-Content -Path $out -Value ("=" * 90)
  Add-Content -Path $out -Value $content
}

Add-Section "GEOPILOT DEM INGESTION / TERRAIN ACCEPTANCE AUDIT" @"
Purpose: inspect current raster upload/registration paths before adding DEM ingestion.
READ-ONLY. No .env, credentials, database mutations, uploads, or source edits.
Generated: $(Get-Date -Format o)
"@

$files = @(
  ".\backend\app\main.py",
  ".\backend\app\api\v1\track_b.py",
  ".\backend\app\api\v1\rasters.py",
  ".\backend\app\services\track_b.py",
  ".\backend\app\services\rasters.py",
  ".\backend\app\services\terrain_analysis.py",
  ".\backend\app\services\data_requirement_router.py",
  ".\backend\app\services\planning_tools.py",
  ".\backend\app\services\planning_orchestrator.py",
  ".\backend\app\models\raster.py",
  ".\backend\app\schemas\raster.py",
  ".\backend\app\schemas\track_b.py",
  ".\frontend\src\lib\api\trackB.ts",
  ".\frontend\src\pages\TrackBWorkspacePage.tsx"
)

foreach ($f in $files) {
  if (Test-Path $f) {
    Add-Section $f (Get-Content $f -Raw)
  } else {
    Add-Section $f "NOT FOUND"
  }
}

$routes = docker compose exec -T backend python -c @"
from app.main import app
for r in app.routes:
    p=getattr(r,'path','')
    m=','.join(sorted(getattr(r,'methods',[]) or []))
    if any(x in p.lower() for x in ('raster','track-b','planning-runs','terrain')):
        print(f'{m:20} {p}')
"@
Add-Section "RUNTIME RELEVANT API ROUTES" ($routes | Out-String)

$project = "f7617e94-7d8c-47d0-8bed-635cf2f48579"
$runtime = docker compose exec -T backend python -c @"
import uuid
from sqlalchemy import select
from app.db.session import get_session_factory
from app.models.raster import RasterDataset

pid=uuid.UUID('$project')
s=get_session_factory()()
try:
    rows=list(s.scalars(select(RasterDataset).where(
        RasterDataset.project_id==pid,
        RasterDataset.is_archived.is_(False)
    ).order_by(RasterDataset.created_at.asc())))
    print('ACTIVE RASTER COUNT:',len(rows))
    for x in rows:
        p=x.provenance or {}
        print(
            x.id,
            '|',x.name,
            '| site=',x.site_id,
            '| source_kind=',x.source_kind,
            '| crs=',x.crs,
            '| bands=',x.band_names,
            '| source_uri=',x.source_uri,
            '| data_role=',p.get('data_role'),
            '| terrain_type=',p.get('terrain_type'),
            '| location_type=',p.get('location_type'),
            '| temporal_role=',p.get('temporal_role'),
            '| stage=',p.get('data_stage'),
        )
finally:
    s.close()
"@
Add-Section "CURRENT PROJECT RASTER INVENTORY" ($runtime | Out-String)

$storage = docker compose exec -T backend python -c @"
from app.core.config import get_settings
from pathlib import Path
s=get_settings()
root=Path(s.raster_storage_root)
print('RASTER_STORAGE_ROOT=',root)
print('EXISTS=',root.exists())
if root.exists():
    for p in sorted(root.rglob('*')):
        if p.is_file():
            try:
                rel=p.relative_to(root)
            except Exception:
                rel=p
            if len(str(rel)) < 300:
                print(rel)
"@
Add-Section "RASTER STORAGE INVENTORY (FILENAMES ONLY)" ($storage | Out-String)

$symbols = Select-String `
  -Path ".\backend\app\**\*.py", ".\frontend\src\**\*.ts", ".\frontend\src\**\*.tsx" `
  -Pattern "UploadFile|datasets/upload|RasterDatasetCreate|source_uri|raster_storage_root|GeoTIFF|\\.tif|\\.tiff|terrain.site_summary|data_role|terrain_type" `
  -CaseSensitive:$false |
  Select-Object Path,LineNumber,Line

Add-Section "RELEVANT SYMBOL SEARCH" ($symbols | Format-Table -AutoSize | Out-String -Width 320)

Write-Host ""
Write-Host "DEM INGESTION AUDIT CREATED:"
Write-Host (Resolve-Path $out)
Write-Host ""
Write-Host "No source files, .env, database rows, or raster files were modified."
