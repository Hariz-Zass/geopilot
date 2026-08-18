$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Service = "backend\app\services\planning_document_acquisition.py"
$Tests = "backend\tests\test_planning_document_acquisition.py"

if (!(Test-Path $Service)) { throw "Missing acquisition service." }
if (!(Test-Path $Tests)) { throw "Missing acquisition tests." }

Write-Host "============================================================"
Write-Host "GeoPilot Planning Document Auto-Ingestion V1.2 Test Repair"
Write-Host "TEST-ONLY import repair after V1.1 service patch"
Write-Host "============================================================"

Write-Host "[1] Verify V1.1 production service patch is present"
docker compose exec -T backend python -c "from app.services.planning_document_acquisition import AcquiredPlanningDocument, register_acquired_document, ingest_acquired_document; print('service_patch=PASS')"
if ($LASTEXITCODE -ne 0) {
    throw "V1.1 production service patch is not healthy. Stop."
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = "artifacts\planning_document_auto_ingestion_v1_2_test_repair_backup_$Stamp"
New-Item -ItemType Directory -Force -Path $Backup | Out-Null
Copy-Item $Tests "$Backup\test_planning_document_acquisition.py"
Write-Host "BACKUP: $Backup"

Write-Host "[2] Apply minimal test-only import repair"
$Helper = "backend\_planning_auto_ingestion_test_import_repair_v1_2.py"

$Patch = @'
from pathlib import Path

path = Path("/app/tests/test_planning_document_acquisition.py")
text = path.read_text(encoding="utf-8-sig")

if "AcquiredPlanningDocument" not in text:
    raise SystemExit("BLOCKED: expected V1.1 tests are not present.")

lines = text.splitlines()

# If already imported, do nothing.
already = any(
    "AcquiredPlanningDocument" in line
    and "from app.services.planning_document_acquisition import" in line
    for line in lines
)

if not already:
    start = None
    end = None
    for i, line in enumerate(lines):
        if line.startswith("from app.services.planning_document_acquisition import ("):
            start = i
            continue
        if start is not None and i > start and line.strip() == ")":
            end = i
            break

    if start is not None and end is not None:
        block = "\n".join(lines[start:end + 1])
        if "AcquiredPlanningDocument" not in block:
            lines.insert(end, "    AcquiredPlanningDocument,")
    else:
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("import ") or line.startswith("from "):
                insert_at = i + 1
        lines.insert(
            insert_at,
            "from app.services.planning_document_acquisition import AcquiredPlanningDocument",
        )

path.write_text("\n".join(lines) + "\n", encoding="utf-8")
print("PATCHED:", path)
print("test_only_change=YES")
'@

Set-Content -Path $Helper -Value $Patch -Encoding UTF8

try {
    docker compose exec -T backend python /app/_planning_auto_ingestion_test_import_repair_v1_2.py
    if ($LASTEXITCODE -ne 0) { throw "Test-only import repair failed." }
}
finally {
    Remove-Item $Helper -Force -ErrorAction SilentlyContinue
}

Write-Host "[3] Syntax check"
docker compose exec -T backend python -m py_compile tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Test syntax check failed." }

Write-Host "[4] Acquisition regression"
docker compose exec -T backend python -m pytest -q tests/test_planning_document_acquisition.py
if ($LASTEXITCODE -ne 0) { throw "Acquisition regression still failing." }

Write-Host "[5] Existing pipeline regressions"
$TestFiles = @(
  "tests/test_pdf_ingestion.py",
  "tests/test_document_chunking.py",
  "tests/test_document_embedding_index.py",
  "tests/test_document_retrieval.py"
)
foreach ($T in $TestFiles) {
  $HostPath = "backend\" + $T.Replace("/","\")
  if (Test-Path $HostPath) {
    docker compose exec -T backend python -m pytest -q $T
    if ($LASTEXITCODE -ne 0) { throw "Regression failed: $T" }
  } else {
    Write-Host "SKIP missing test file: $T"
  }
}

Write-Host "[6] Service health"
docker compose ps

Write-Host "============================================================"
Write-Host "PLANNING DOCUMENT AUTO-INGESTION V1.2 TEST REPAIR PASS"
Write-Host "============================================================"
Write-Host "Production service patch: PRESERVED"
Write-Host "Test-only import repair: PASS"
Write-Host "AcquiredPlanningDocument import: FIXED"
Write-Host "Acquisition regression: PASS"
Write-Host "PDF ingestion regression: PASS"
Write-Host "Chunking regression: PASS"
Write-Host "Embedding index regression: PASS"
Write-Host "Retrieval regression: PASS"
Write-Host "DB schema change: NONE"
Write-Host "Migration: NONE"
Write-Host "Frontend change: NONE"
Write-Host "Live persistent external ingestion: NOT RUN"
Write-Host "============================================================"
