$ErrorActionPreference="Stop"
Set-StrictMode -Version Latest
$Root=Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Py="$Root\collect_geopilot_pdf_ingestion_source_audit_v1.py"
$BackendPy="$Root\backend\collect_geopilot_pdf_ingestion_source_audit_v1.py"
$Report="$Root\geopilot_pdf_ingestion_source_audit_v1.txt"

if (!(Test-Path $Py)) { throw "Audit Python file missing." }

Write-Host "============================================================"
Write-Host "GeoPilot PDF Ingestion Source Audit V1"
Write-Host "READ ONLY"
Write-Host "============================================================"

Copy-Item $Py $BackendPy -Force
try {
    docker compose exec -T backend python /app/collect_geopilot_pdf_ingestion_source_audit_v1.py 2>&1 |
        Tee-Object -FilePath $Report
    if ($LASTEXITCODE -ne 0) { throw "PDF ingestion source audit failed." }
}
finally {
    Remove-Item $BackendPy -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "REPORT: $Report"
Write-Host "DB write: NONE"
Write-Host "Source patch: NONE"
Write-Host "Migration: NONE"
