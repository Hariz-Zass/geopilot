
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$out = ".\geopilot_capability_upgrade_audit.txt"
if (Test-Path $out) { Remove-Item $out -Force }

function Add-Section([string]$title, [string]$content) {
  Add-Content -Path $out -Value ""
  Add-Content -Path $out -Value ("=" * 90)
  Add-Content -Path $out -Value $title
  Add-Content -Path $out -Value ("=" * 90)
  Add-Content -Path $out -Value $content
}

Add-Section "GEOPILOT CAPABILITY UPGRADE AUDIT" @"
Purpose: inspect current architecture before adding Data Requirement Router + Terrain Intelligence.
READ-ONLY collector. No .env or API keys are collected.
Generated: $(Get-Date -Format o)
"@

$explicit = @(
  ".\backend\app\services\planning_orchestrator.py",
  ".\backend\app\services\provider_resilience.py",
  ".\backend\app\services\rasters.py",
  ".\backend\app\services\gis.py",
  ".\backend\app\services\spatial.py",
  ".\backend\app\models\raster.py",
  ".\backend\app\models\gis.py",
  ".\backend\app\schemas\raster.py",
  ".\backend\app\schemas\gis.py",
  ".\backend\app\api\v1\planning.py",
  ".\backend\app\api\v1\gis.py",
  ".\backend\app\api\v1\rasters.py"
)

foreach ($f in $explicit) {
  if (Test-Path $f) {
    Add-Section $f (Get-Content $f -Raw)
  }
}

# Discover current server-owned tool registry / GIS / planning files by name.
$patterns = @(
  "*tool*.py",
  "*planning*.py",
  "*gis*.py",
  "*spatial*.py",
  "*raster*.py"
)

$found = @()
foreach ($pattern in $patterns) {
  $found += Get-ChildItem ".\backend\app" -Recurse -File -Filter $pattern
}
$found = $found | Sort-Object FullName -Unique

foreach ($f in $found) {
  if ($explicit -contains $f.FullName) { continue }
  $relative = $f.FullName.Substring($PSScriptRoot.Length).TrimStart("\")
  Add-Section $relative (Get-Content $f.FullName -Raw)
}

# Relevant tests.
$tests = Get-ChildItem ".\backend\tests" -File -Filter "*.py" |
  Where-Object { $_.Name -match "planning|tool|gis|spatial|raster|track_b" } |
  Sort-Object Name

foreach ($f in $tests) {
  Add-Section ("backend\tests\" + $f.Name) (Get-Content $f.FullName -Raw)
}

# Search routes/capability symbols without collecting secrets.
$search = Select-String `
  -Path ".\backend\app\**\*.py" `
  -Pattern "ToolRegistry|tool_registry|buffer|intersect|intersection|distance|nearest|overlay|slope|elevation|DEM|terrain|RasterDataset|PlanningRun|planner_question" `
  -CaseSensitive:$false |
  Select-Object Path,LineNumber,Line

Add-Section "SYMBOL SEARCH" ($search | Format-Table -AutoSize | Out-String -Width 300)

# Runtime package capability.
$runtime = docker compose exec -T backend python -c @"
import importlib.util
mods=['rasterio','numpy','pyproj','shapely','scipy','geopandas']
for m in mods:
    print(m, 'YES' if importlib.util.find_spec(m) else 'NO')
"@
Add-Section "RUNTIME GEOSPATIAL PACKAGES" ($runtime | Out-String)

# Current tests only; no modifications.
$testList = docker compose exec -T backend python -m pytest --collect-only -q 2>&1 |
  Select-String -Pattern "planning|gis|spatial|raster|track_b"
Add-Section "RELEVANT TEST COLLECTION" ($testList | Out-String)

Write-Host ""
Write-Host "AUDIT BUNDLE CREATED:"
Write-Host (Resolve-Path $out)
Write-Host ""
Write-Host "No .env or API keys were collected."
