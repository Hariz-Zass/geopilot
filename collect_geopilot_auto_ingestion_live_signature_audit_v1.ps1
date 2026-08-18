$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Py = Join-Path $Root "collect_geopilot_auto_ingestion_live_signature_audit_v1.py"
$BackendPy = Join-Path $Root "backend\collect_geopilot_auto_ingestion_live_signature_audit_v1.py"
$Report = Join-Path $Root "geopilot_auto_ingestion_live_signature_audit_v1.txt"

if (!(Test-Path $Py)) { throw "Audit Python file missing beside BAT/PS1." }

Write-Host "============================================================"
Write-Host "GeoPilot Auto-Ingestion Live Signature Audit V1"
Write-Host "READ ONLY"
Write-Host "============================================================"

Copy-Item $Py $BackendPy -Force
try {
    docker compose exec -T backend python /app/collect_geopilot_auto_ingestion_live_signature_audit_v1.py 2>&1 |
        Tee-Object -FilePath $Report
    if ($LASTEXITCODE -ne 0) { throw "Audit failed." }
}
finally {
    Remove-Item $BackendPy -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "============================================================"
Write-Host "AUTO-INGESTION LIVE SIGNATURE AUDIT V1 PASS"
Write-Host "============================================================"
Write-Host "DB write: NONE"
Write-Host "Migration: NONE"
Write-Host "Source patch: NONE"
Write-Host "REPORT: $Report"
Write-Host "============================================================"
