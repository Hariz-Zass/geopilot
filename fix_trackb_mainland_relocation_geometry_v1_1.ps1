
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "============================================================"
Write-Host "GeoPilot Urban Mainland Relocation Geometry Fix V1.1"
Write-Host "Fixes canonical_multipolygon input type only"
Write-Host "============================================================"
Write-Host ""

$target = ".\relocate_trackb_urban_to_shah_alam_v1.ps1"
if (-not (Test-Path $target)) {
    throw "Original relocation script not found: $target"
}

Write-Host "[1/3] Confirming previous failed run made no DB mutation..."
docker compose exec -T backend python -c "import uuid; from sqlalchemy import select; from app.db.session import get_session_factory; from app.models.site import Site; s=get_session_factory()(); x=s.scalar(select(Site).where(Site.id==uuid.UUID('2ea1e98d-347c-4a0a-8e5b-5dd7f9553673'))); print('GEOMETRY_REVISION=',x.geometry_revision); print('GEOMETRY=',x.geometry); assert x.geometry_revision==1; assert '101.249490680555' in str(x.geometry); s.close()"
if ($LASTEXITCODE -ne 0) {
    throw "Baseline is no longer the expected pre-relocation state. STOP."
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = ".\artifacts\relocation_script_geometry_fix_$stamp"
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Copy-Item $target "$backup\relocate_trackb_urban_to_shah_alam_v1.ps1"

Write-Host ""
Write-Host "[2/3] Applying exact geometry-object patch..."
$text = Get-Content $target -Raw

$oldImport = "import uuid, hashlib, os, json"
$newImport = "import uuid, hashlib, os, json`nfrom types import SimpleNamespace"

if ($text.Contains($oldImport) -and -not $text.Contains("from types import SimpleNamespace")) {
    $text = $text.Replace($oldImport, $newImport)
}

$oldGeometry = "geometry={'type':'Polygon','coordinates':[[[minlon,minlat],[maxlon,minlat],[maxlon,maxlat],[minlon,maxlat],[minlon,minlat]]]}`ncoords=canonical_multipolygon(geometry)"
$newGeometry = "geometry=SimpleNamespace(type='Polygon',coordinates=[[[minlon,minlat],[maxlon,minlat],[maxlon,maxlat],[minlon,maxlat],[minlon,minlat]]])`ncoords=canonical_multipolygon(geometry)"

if (-not $text.Contains($oldGeometry)) {
    throw "Expected geometry block not found. STOP to avoid blind patch."
}

$text = $text.Replace($oldGeometry, $newGeometry)
Set-Content -Path $target -Value $text -Encoding UTF8

Write-Host "BACKUP: $backup"
Write-Host "PATCHED: $target"

Write-Host ""
Write-Host "[3/3] Running corrected controlled relocation..."
powershell -NoProfile -ExecutionPolicy Bypass -File $target
if ($LASTEXITCODE -ne 0) {
    throw "Corrected relocation still failed. Do not rerun blindly."
}

Write-Host ""
Write-Host "============================================================"
Write-Host "URBAN MAINLAND RELOCATION GEOMETRY FIX V1.1 PASS"
Write-Host "============================================================"
