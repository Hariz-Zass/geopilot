$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Py="$Root\collect_geopilot_embedding_provider_live_preflight_v1.py"
$BackendPy="$Root\backend\collect_geopilot_embedding_provider_live_preflight_v1.py"
$Report="$Root\geopilot_embedding_provider_live_preflight_v1.txt"

if(!(Test-Path $Py)){ throw "Preflight Python file missing." }

Write-Host "============================================================"
Write-Host "GeoPilot Embedding Provider Live Preflight V1"
Write-Host "READ ONLY - NO ENV/SOURCE/DB CHANGE"
Write-Host "============================================================"

Write-Host "[0] Service health"
docker compose ps

Copy-Item $Py $BackendPy -Force
try {
  Write-Host "[1] Run live embedding preflight"
  docker compose exec -T backend python /app/collect_geopilot_embedding_provider_live_preflight_v1.py 2>&1 |
    Tee-Object -FilePath $Report
  $Code=$LASTEXITCODE
}
finally {
  Remove-Item $BackendPy -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "REPORT: $Report"
Write-Host "ENV change: NONE"
Write-Host "Source change: NONE"
Write-Host "DB write: NONE"
Write-Host "Migration: NONE"

if($Code -eq 0){
  Write-Host "PREFLIGHT COMPLETED"
  exit 0
}
throw "Embedding preflight returned diagnostic exit code $Code. Paste the complete report into ChatGPT."
