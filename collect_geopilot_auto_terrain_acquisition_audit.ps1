
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================"
Write-Host "GeoPilot Automatic Terrain Acquisition Audit V1"
Write-Host "READ-ONLY capability audit"
Write-Host "No API keys, .env values, DB rows, or source files modified"
Write-Host "============================================================"
Write-Host ""

$out = ".\geopilot_auto_terrain_acquisition_audit.txt"
if (Test-Path $out) { Remove-Item $out -Force }

function Add-Section([string]$title, [string]$content) {
    Add-Content -Path $out -Value ""
    Add-Content -Path $out -Value ("=" * 92)
    Add-Content -Path $out -Value $title
    Add-Content -Path $out -Value ("=" * 92)
    Add-Content -Path $out -Value $content
}

Add-Section "AUDIT INTENT" @"
Goal:
1. Preserve existing manual/user-supplied DEM as highest-priority terrain evidence.
2. Add automatic terrain acquisition as fallback when a Site has no ready DEM.
3. Keep provider provenance, checksum, resolution, CRS, source product, and acquisition metadata.
4. Feed deterministic terrain.site_summary evidence into Planning Copilot.
5. Do not modify Track B competition workflow or organizer-only evidence semantics.
"@

$targets = @(
    ".\backend\app\core\config.py",
    ".\backend\app\services\terrain_analysis.py",
    ".\backend\app\services\terrain_ingestion.py",
    ".\backend\app\services\data_requirement_router.py",
    ".\backend\app\services\planning_tools.py",
    ".\backend\app\services\planning_orchestrator.py",
    ".\backend\app\api\v1\terrain.py",
    ".\backend\app\api\v1\router.py",
    ".\backend\app\models\raster.py",
    ".\backend\app\models\site.py",
    ".\backend\requirements.txt",
    ".\backend\pyproject.toml",
    ".\docker-compose.yml",
    ".\compose.yml"
)

foreach ($f in $targets) {
    if (Test-Path $f) {
        Add-Section $f (Get-Content $f -Raw)
    } else {
        Add-Section $f "NOT FOUND"
    }
}

# Capture frontend integration surface if present.
$frontendFiles = Get-ChildItem ".\frontend\src" -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -match 'planning|terrain|api|workspace|project|site' -and
        $_.Extension -in @(".ts",".tsx")
    } |
    Select-Object -First 30

foreach ($f in $frontendFiles) {
    Add-Section $f.FullName (Get-Content $f.FullName -Raw)
}

# Environment variable NAMES ONLY. Never values.
$envNames = @()
foreach ($candidate in @(".\.env",".\.env.local",".\backend\.env",".\frontend\.env")) {
    if (Test-Path $candidate) {
        $names = Get-Content $candidate |
            Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } |
            ForEach-Object { ($_ -split '=',2)[0] }
        foreach ($n in $names) {
            $envNames += "$candidate :: $n"
        }
    }
}
Add-Section "ENV VARIABLE NAMES ONLY" (($envNames | Sort-Object -Unique) -join "`r`n")

# Installed libraries relevant to HTTP, raster, STAC and cloud access.
$pkgs = docker compose exec -T backend python -c @"
import importlib.util
mods=['httpx','requests','pystac_client','rasterio','rio_tiler','boto3','botocore','shapely','pyproj']
for m in mods:
    print(m, 'YES' if importlib.util.find_spec(m) else 'NO')
"@
Add-Section "BACKEND LIBRARY AVAILABILITY" ($pkgs | Out-String)

# Current terrain endpoint + planning route surface.
$routes = docker compose exec -T backend python -c @"
from app.main import app
for r in app.routes:
    p=getattr(r,'path','')
    if any(k in p.lower() for k in ('terrain','planning')):
        print(p, sorted(list(getattr(r,'methods',[]) or [])))
"@
Add-Section "RUNTIME TERRAIN/PLANNING ROUTES" ($routes | Out-String)

# Current project/site DEM inventory and site state, no secrets.
$inventory = docker compose exec -T backend python -c @"
import uuid, json
from sqlalchemy import select
from app.db.session import get_session_factory
from app.models.site import Site
from app.models.raster import RasterDataset

pid=uuid.UUID('f7617e94-7d8c-47d0-8bed-635cf2f48579')
sid=uuid.UUID('2ea1e98d-347c-4a0a-8e5b-5dd7f9553673')
s=get_session_factory()()
try:
    site=s.scalar(select(Site).where(Site.id==sid,Site.project_id==pid))
    print('SITE_ID=',site.id)
    print('SITE_NAME=',site.name)
    print('SITE_ACTIVE=',site.is_active)
    print('SITE_ARCHIVED=',site.is_archived)
    print('SITE_GEOMETRY_REVISION=',site.geometry_revision)
    print('SITE_GEOMETRY=',site.geometry)
    print()
    rows=list(s.scalars(select(RasterDataset).where(
        RasterDataset.project_id==pid,
        RasterDataset.site_id==sid,
        RasterDataset.is_archived.is_(False)
    ).order_by(RasterDataset.created_at.asc())))
    for x in rows:
        p=x.provenance or {}
        print('RASTER_ID=',x.id)
        print(' NAME=',x.name)
        print(' STATUS=',x.status)
        print(' CRS=',x.crs)
        print(' BANDS=',x.band_names)
        print(' RESOLUTION=',x.pixel_size)
        print(' BOUNDS=',x.bounds)
        print(' DATA_ROLE=',p.get('data_role'))
        print(' TERRAIN_TYPE=',p.get('terrain_type'))
        print(' EVIDENCE_SCOPE=',p.get('evidence_scope'))
        print(' INGESTION_METHOD=',p.get('ingestion_method'))
        print(' PROVIDER=',x.provider)
        print(' COLLECTION=',x.collection)
        print()
finally:
    s.close()
"@
Add-Section "CURRENT SHAH ALAM SITE + RASTER INVENTORY" ($inventory | Out-String)

# Source references to outbound HTTP/network code patterns.
$networkScan = Get-ChildItem ".\backend\app" -Recurse -File -Filter "*.py" |
    Select-String -Pattern "httpx|requests\.|AsyncClient|Client\(|boto3|pystac|stac|sentinelhub|dataspace|copernicus|download" |
    ForEach-Object { "$($_.Path):$($_.LineNumber): $($_.Line.Trim())" }
Add-Section "EXISTING NETWORK/PROVIDER PATTERNS" (($networkScan | Select-Object -First 400) -join "`r`n")

Write-Host ""
Write-Host "AUDIT CREATED:"
Write-Host (Resolve-Path $out)
Write-Host ""
Write-Host "No source files, database rows, raster files, or secret values were modified/collected."
