
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$out = ".\trackb_mainland_relocation_preflight.txt"
if (Test-Path $out) { Remove-Item $out -Force }

function Add-Section([string]$title, [string]$content) {
    Add-Content -Path $out -Value ""
    Add-Content -Path $out -Value ("=" * 90)
    Add-Content -Path $out -Value $title
    Add-Content -Path $out -Value ("=" * 90)
    Add-Content -Path $out -Value $content
}

Add-Section "TRACK B MAINLAND RELOCATION PREFLIGHT" @"
READ-ONLY.
Goal: relocate Urban QA demo from coastal/island context to a verified mainland Shah Alam demo extent
without touching Rural QA, Track B logic, or analysis semantics.
No files or DB rows are modified.
"@

$files = @(
  ".\backend\app\models\site.py",
  ".\backend\app\services\sites.py",
  ".\backend\app\services\track_b_acceptance.py",
  ".\backend\app\services\track_b_workflow.py"
)

foreach ($f in $files) {
    if (Test-Path $f) {
        Add-Section $f (Get-Content $f -Raw)
    } else {
        Add-Section $f "NOT FOUND"
    }
}

$runtime = docker compose exec -T backend python -c @"
import uuid, json
from sqlalchemy import select
from app.db.session import get_session_factory
from app.models.site import Site
from app.models.raster import RasterDataset

PROJECT_ID=uuid.UUID('f7617e94-7d8c-47d0-8bed-635cf2f48579')
SITE_ID=uuid.UUID('2ea1e98d-347c-4a0a-8e5b-5dd7f9553673')

s=get_session_factory()()
try:
    site=s.scalar(select(Site).where(Site.id==SITE_ID, Site.project_id==PROJECT_ID))
    print('SITE:')
    for key in ('id','name','is_active','is_archived','geometry','geometry_hash','geometry_revision','created_at','updated_at'):
        if hasattr(site,key):
            print(' ',key,'=',getattr(site,key))

    print()
    print('URBAN RASTERS:')
    rows=list(s.scalars(select(RasterDataset).where(
        RasterDataset.project_id==PROJECT_ID,
        RasterDataset.site_id==SITE_ID,
        RasterDataset.is_archived.is_(False)
    ).order_by(RasterDataset.created_at.asc())))
    for x in rows:
        print(' ID=',x.id)
        print(' NAME=',x.name)
        print(' CRS=',x.crs)
        print(' SIZE=',x.width,x.height)
        print(' BANDS=',x.band_names)
        print(' PIXEL=',x.pixel_size)
        print(' BOUNDS=',x.bounds)
        print(' URI=',x.source_uri)
        print(' SHA=',x.checksum_sha256)
        print(' PROVENANCE=',json.dumps(x.provenance or {},sort_keys=True,default=str))
        print()
finally:
    s.close()
"@
Add-Section "LIVE SITE + URBAN RASTER BASELINE" ($runtime | Out-String)

$filesRuntime = docker compose exec -T backend python -c @"
import uuid, hashlib
from pathlib import Path
from sqlalchemy import select
from app.core.config import get_settings
from app.db.session import get_session_factory
from app.models.raster import RasterDataset

PROJECT_ID=uuid.UUID('f7617e94-7d8c-47d0-8bed-635cf2f48579')
SITE_ID=uuid.UUID('2ea1e98d-347c-4a0a-8e5b-5dd7f9553673')
root=Path(get_settings().raster_storage_root).resolve()
s=get_session_factory()()
try:
    rows=list(s.scalars(select(RasterDataset).where(
        RasterDataset.project_id==PROJECT_ID,
        RasterDataset.site_id==SITE_ID,
        RasterDataset.is_archived.is_(False)
    )))
    for x in rows:
        uri=x.source_uri or ''
        print(x.id,x.name)
        if uri.startswith('local://rasters/'):
            p=(root / uri[len('local://rasters/'):]).resolve()
            print(' PATH=',p)
            print(' EXISTS=',p.is_file())
            if p.is_file():
                print(' FILE_SHA=',hashlib.sha256(p.read_bytes()).hexdigest())
                print(' DB_SHA=',x.checksum_sha256)
        else:
            print(' NON_LOCAL_URI=',uri)
finally:
    s.close()
"@
Add-Section "IMMUTABLE FILE CHECK" ($filesRuntime | Out-String)

Write-Host ""
Write-Host "PREFLIGHT CREATED:"
Write-Host (Resolve-Path $out)
Write-Host ""
Write-Host "No source files, raster files, or database rows were modified."
