$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$SourcePy = Join-Path $Root "collect_geopilot_official_catalogue_live_structure_v1.py"
$BackendPy = Join-Path $Root "backend\collect_geopilot_official_catalogue_live_structure_v1.py"
$Report = Join-Path $Root "geopilot_official_catalogue_live_structure_v1.txt"

if (!(Test-Path $SourcePy)) {
    throw "collect_geopilot_official_catalogue_live_structure_v1.py not found beside this installer."
}

Write-Host "============================================================"
Write-Host "GeoPilot Official Catalogue Live Structure V1.1"
Write-Host "Backend bind-mount recovery"
Write-Host "READ ONLY"
Write-Host "============================================================"
Write-Host ""

Copy-Item $SourcePy $BackendPy -Force
Write-Host "[1] Temporary audit script copied into backend bind mount"
Write-Host "    backend\collect_geopilot_official_catalogue_live_structure_v1.py"

try {
    Write-Host ""
    Write-Host "[2] Run live official catalogue audit"
    docker compose exec -T backend python /app/collect_geopilot_official_catalogue_live_structure_v1.py 2>&1 |
        Tee-Object -FilePath $Report

    if ($LASTEXITCODE -ne 0) {
        throw "Live catalogue audit failed with exit code $LASTEXITCODE."
    }

    Write-Host ""
    Write-Host "[3] Audit completed"
    Write-Host "REPORT: $Report"
}
finally {
    if (Test-Path $BackendPy) {
        Remove-Item $BackendPy -Force
        Write-Host ""
        Write-Host "[4] Temporary backend audit script removed"
    }
}

Write-Host ""
Write-Host "============================================================"
Write-Host "OFFICIAL CATALOGUE LIVE STRUCTURE V1.1 PASS"
Write-Host "============================================================"
Write-Host "DB write: NONE"
Write-Host "Migration: NONE"
Write-Host "Persistent source patch: NONE"
Write-Host "Temporary backend audit file: CLEANED UP"
Write-Host "============================================================"
