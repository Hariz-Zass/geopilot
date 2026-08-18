$ErrorActionPreference = "Stop"
Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer ZIP V1.2.2"
Write-Host "Compatibility repair against actual Phase 1.1 service symbols"
Write-Host "NO DB WRITE / NO MIGRATION"
Write-Host "============================================================"

$root=(Get-Location).Path
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root "artifacts\smart_organizer_zip_v1_2_2_backup_$stamp"
$service=Join-Path $root "backend\app\services\track_b_smart_intake.py"
$test=Join-Path $root "backend\tests\test_track_b_smart_organizer_zip_v1_2_2.py"

if(-not (Test-Path $service)){throw "Phase 1.1 service not found."}
New-Item -ItemType Directory -Force $backup | Out-Null
Copy-Item $service (Join-Path $backup "track_b_smart_intake.py") -Force

function Restore-Backup {
  Copy-Item (Join-Path $backup "track_b_smart_intake.py") $service -Force
  if(Test-Path $test){Remove-Item $test -Force}
}

try {
  Write-Host "BACKUP: $backup"
  Write-Host "[0] Confirm clean Phase 1.1 rollback baseline"
  $t=Get-Content $service -Raw
  foreach($symbol in @("def _base(","def _stage(","def _band(","def _geojson(","_DEM =","async def inspect_organizer_package")){
    if(-not $t.Contains($symbol)){throw "Expected Phase 1.1 symbol missing: $symbol"}
  }
  if($t.Contains("SMART_ORGANIZER_ZIP_V1_2_2")){throw "V1.2.2 already installed."}
  Write-Host "actual_phase1_1_symbols=CONFIRMED"

  Write-Host "[1] Append V1.2.2 recursive ZIP inspector using actual Phase 1.1 symbols"
  @'

# SMART_ORGANIZER_ZIP_V1_2_2
_ZIP_SUPPORTED_SUFFIXES = {".tif", ".tiff", ".jp2", ".zip", ".geojson", ".json", ".pdf", ".csv"}
_ZIP_MAX_MEMBERS = 1000
_ZIP_MAX_DEPTH = 2

def _zip_base(member_name: str, index: int, archive_name: str) -> dict[str, Any]:
    class _MemberUpload:
        filename = member_name
        content_type = None
    item = _base(_MemberUpload(), index)
    item["archive_path"] = member_name
    item["source_archive"] = archive_name
    return item

def _zip_member_item(member_name: str, data: bytes, index: int, archive_name: str) -> dict[str, Any]:
    item = _zip_base(member_name, index, archive_name)
    item["size_bytes"] = len(data)
    suffix = item["extension"]
    normalized = _norm(member_name)

    if suffix in {".tif", ".tiff", ".jp2"}:
        item["data_stage"] = _stage(normalized, True)
        try:
            r = _inspect_bytes(data)
            item["metadata"] = {
                "crs": r.crs, "width": r.width, "height": r.height,
                "band_count": r.count, "band_names": r.band_names,
                "pixel_size": r.pixel_size, "bounds": r.bounds,
                "driver": r.driver, "dtype": r.dtype,
            }
            if any(x in normalized for x in _DEM) and r.count == 1:
                item["classification"] = "terrain_dem_candidate"
                item["confidence"] = "high"
                item["requires_confirmation"] = True
                item["issues"].append("DEM candidate requires Site assignment and Terrain Engine validation.")
            elif item["band_name"] and r.count == 1:
                item["classification"] = "raster_band_candidate"
                item["confidence"] = "high"
                item["requires_confirmation"] = not (item["location_type"] and item["temporal_role"])
            else:
                item["classification"] = "raster_dataset_candidate"
                item["confidence"] = "high"
                item["requires_confirmation"] = not (item["location_type"] and item["temporal_role"])
        except Exception as exc:
            item["classification"] = "invalid_raster"
            item["confidence"] = "high"
            item["requires_confirmation"] = True
            item["issues"].append(str(exc))

    elif suffix in {".geojson", ".json"}:
        _geojson(item, data)

    elif suffix == ".pdf":
        item["classification"] = "planning_document_candidate"
        item["confidence"] = "high"
        item["requires_confirmation"] = True
        item["metadata"] = {"document_class_required": True}
        item["issues"].append("Confirm RFN/RSN/RT/RKK/GPP/other class and registration metadata before import.")

    elif suffix == ".csv":
        try:
            header = next(csv.reader(io.StringIO(data.decode("utf-8-sig"))), [])
        except Exception:
            header = []
        item["classification"] = "metadata_helper"
        item["confidence"] = "high"
        item["requires_confirmation"] = False
        item["metadata"] = {"columns": header[:50]}
        item["issues"].append("CSV is helper metadata only in Smart Intake V1.2.2.")

    else:
        item["classification"] = "unsupported"
        item["confidence"] = "high"
        item["requires_confirmation"] = False
        item["issues"].append(f"Archive member extension is unsupported: {suffix or 'none'}.")

    return item

def _inspect_zip_members(
    archive_name: str,
    data: bytes,
    *,
    depth: int = 0,
    start_index: int = 0,
) -> list[dict[str, Any]]:
    if depth > _ZIP_MAX_DEPTH:
        item = _zip_base(archive_name, start_index, archive_name)
        item["size_bytes"] = len(data)
        item["classification"] = "archive_depth_blocked"
        item["confidence"] = "high"
        item["requires_confirmation"] = True
        item["issues"].append("Nested ZIP depth exceeds Smart Intake safety limit.")
        return [item]

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, RuntimeError):
        item = _zip_base(archive_name, start_index, archive_name)
        item["size_bytes"] = len(data)
        item["classification"] = "invalid_archive"
        item["confidence"] = "high"
        item["requires_confirmation"] = True
        item["issues"].append("ZIP file is not a readable archive.")
        return [item]

    infos = [x for x in archive.infolist() if not x.is_dir()]
    if len(infos) > _ZIP_MAX_MEMBERS:
        raise TrackBError(f"Organizer ZIP contains more than {_ZIP_MAX_MEMBERS} files.")

    limit = max(
        int(get_settings().raster_upload_max_bytes),
        int(get_settings().document_upload_max_bytes),
    )
    results = []
    index = start_index

    for info in infos:
        member = info.filename.replace("\\", "/")
        parts = [x for x in member.split("/") if x not in {"", "."}]

        if ".." in parts or member.startswith("/"):
            item = _zip_base(member, index, archive_name)
            item["size_bytes"] = int(info.file_size)
            item["classification"] = "unsafe_archive_path"
            item["confidence"] = "high"
            item["requires_confirmation"] = True
            item["issues"].append("Unsafe archive path was blocked; no extraction occurred.")
            results.append(item)
            index += 1
            continue

        suffix = Path(member).suffix.casefold()

        if suffix not in _ZIP_SUPPORTED_SUFFIXES:
            results.append(_zip_member_item(member, b"", index, archive_name))
            index += 1
            continue

        if info.file_size > limit:
            item = _zip_base(member, index, archive_name)
            item["size_bytes"] = int(info.file_size)
            item["classification"] = "too_large"
            item["confidence"] = "high"
            item["requires_confirmation"] = True
            item["issues"].append("Archive member exceeds configured Smart Intake per-file limit.")
            results.append(item)
            index += 1
            continue

        member_data = archive.read(info)

        if suffix == ".zip":
            nested = _inspect_zip_members(
                f"{archive_name}:{member}",
                member_data,
                depth=depth + 1,
                start_index=index,
            )
            results.extend(nested)
            index += max(1, len(nested))
        else:
            results.append(_zip_member_item(member, member_data, index, archive_name))
            index += 1

    return results

_inspect_organizer_package_phase1_1 = inspect_organizer_package

async def inspect_organizer_package(files: list[UploadFile]) -> dict[str, Any]:
    if not files:
        raise TrackBError("Organizer package inspection requires at least one file.")

    expanded = []
    ordinary = []

    for upload in files:
        if Path(upload.filename or "").suffix.casefold() != ".zip":
            ordinary.append(upload)
            continue

        limit = max(
            int(get_settings().raster_upload_max_bytes),
            int(get_settings().document_upload_max_bytes),
        )
        data = await upload.read(limit + 1)

        if len(data) > limit:
            item = _zip_base(upload.filename or "archive.zip", len(expanded), upload.filename or "archive.zip")
            item["size_bytes"] = len(data)
            item["classification"] = "too_large"
            item["confidence"] = "high"
            item["requires_confirmation"] = True
            item["issues"].append("Organizer ZIP exceeds configured Smart Intake inspection limit.")
            expanded.append(item)
        else:
            expanded.extend(
                _inspect_zip_members(
                    upload.filename or "archive.zip",
                    data,
                    start_index=len(expanded),
                )
            )

    if ordinary:
        base = await _inspect_organizer_package_phase1_1(ordinary)
        for item in base["items"]:
            item["index"] = len(expanded)
            item["archive_path"] = None
            item["source_archive"] = None
            expanded.append(item)

    counts = {}
    for item in expanded:
        counts[item["classification"]] = counts.get(item["classification"], 0) + 1

    blocker_classes = {
        "empty", "too_large", "invalid_raster", "invalid_geojson",
        "invalid_archive", "unsafe_archive_path", "archive_depth_blocked",
    }
    blockers = [
        item["filename"]
        for item in expanded
        if item["classification"] in blocker_classes
    ]

    return {
        "phase": "inspect_only",
        "database_writes": False,
        "file_count": len(expanded),
        "supported_or_reviewable_count": sum(
            item["classification"] not in {"unsupported", "empty", "too_large"}
            for item in expanded
        ),
        "requires_confirmation_count": sum(
            bool(item["requires_confirmation"]) for item in expanded
        ),
        "blocker_count": len(blockers),
        "class_counts": counts,
        "blockers": blockers,
        "items": expanded,
        "next_action": "Review ZIP contents and classifications before Import All.",
        "archive_expansion": True,
    }
'@ | Add-Content $service -Encoding UTF8

  Write-Host "[2] Install compatibility-focused regression"
  @'
from __future__ import annotations
import asyncio, io, json, zipfile
from fastapi import UploadFile
from app.services.track_b_smart_intake import inspect_organizer_package

def up(n,d): return UploadFile(filename=n,file=io.BytesIO(d))
def run(files): return asyncio.run(inspect_organizer_package(files))
def z(entries):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as a:
        for n,d in entries.items(): a.writestr(n,d)
    return b.getvalue()

def test_mixed_zip():
    geo=json.dumps({"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[101,3],[101.1,3],[101.1,3.1],[101,3]]]}}]}).encode()
    r=run([up("Organizer.zip",z({
        "Urban/Planning/urban_zoning.geojson":geo,
        "Documents/RT.pdf":b"%PDF-1.4",
        "metadata.csv":b"name,date\nx,y\n",
        "notes.xyz":b"x",
    }))])
    classes={x["classification"] for x in r["items"]}
    assert r["archive_expansion"] is True
    assert r["database_writes"] is False
    assert {"planning_spatial_candidate","planning_document_candidate","metadata_helper","unsupported"} <= classes

def test_path_hints():
    r=run([up("Organizer.zip",z({"Urban/T1/urban_T1_B04.jp2":b"not-raster"}))])
    x=r["items"][0]
    assert x["location_type"]=="urban"
    assert x["temporal_role"]=="before"
    assert x["band_name"]=="B04"

def test_zip_slip_blocked():
    r=run([up("Organizer.zip",z({"../evil.pdf":b"x"}))])
    assert r["items"][0]["classification"]=="unsafe_archive_path"

def test_nested_zip():
    inner=z({"Documents/GPP.pdf":b"%PDF-1.4"})
    outer=z({"nested/materials.zip":inner})
    r=run([up("Organizer.zip",outer)])
    assert any(x["classification"]=="planning_document_candidate" for x in r["items"])
'@ | Set-Content $test -Encoding UTF8

  Write-Host "[3] Syntax checks"
  docker compose exec -T backend python -m py_compile /app/app/services/track_b_smart_intake.py
  if($LASTEXITCODE-ne 0){throw "Syntax failed."}

  Write-Host "[4] Phase 1.1 regression"
  docker compose exec -T backend python -m pytest -q tests/test_track_b_smart_organizer_intake_v1.py
  if($LASTEXITCODE-ne 0){throw "Phase 1.1 regression failed."}

  Write-Host "[5] ZIP V1.2.2 regression"
  docker compose exec -T backend python -m pytest -q tests/test_track_b_smart_organizer_zip_v1_2_2.py
  if($LASTEXITCODE-ne 0){throw "ZIP V1.2.2 regression failed."}

  Write-Host "[6] Full backend regression"
  docker compose exec -T backend python -m pytest -q
  if($LASTEXITCODE-ne 0){throw "Full backend regression failed."}

  Write-Host "[7] Frontend typecheck/build"
  docker compose exec -T frontend npm run typecheck
  if($LASTEXITCODE-ne 0){throw "Frontend typecheck failed."}
  docker compose exec -T frontend npm run build
  if($LASTEXITCODE-ne 0){throw "Frontend build failed."}

  Write-Host "[8] Recreate backend"
  docker compose up -d --force-recreate backend
  if($LASTEXITCODE-ne 0){throw "Backend recreate failed."}
  Start-Sleep -Seconds 8
  docker compose ps backend

  Write-Host "[9] Runtime contract"
  docker compose exec -T backend python -c "import app.services.track_b_smart_intake as m; from pathlib import Path; t=Path('/app/app/services/track_b_smart_intake.py').read_text(); assert 'SMART_ORGANIZER_ZIP_V1_2_2' in t; assert hasattr(m,'_inspect_zip_members'); print('runtime_zip_v1_2_2=PASS')"
  if($LASTEXITCODE-ne 0){throw "Runtime verification failed."}

  Write-Host "============================================================"
  Write-Host "SMART ORGANIZER ZIP V1.2.2 PASS"
  Write-Host "============================================================"
  Write-Host "Actual Phase 1.1 symbol compatibility: VERIFIED"
  Write-Host "Recursive organizer ZIP inspection: ENABLED"
  Write-Host "Nested ZIP safety depth: ENFORCED"
  Write-Host "Unsafe archive paths: BLOCKED"
  Write-Host "Inspection DB writes: NONE"
  Write-Host "Migration: NONE"
  Write-Host "Next gate: LIVE ORGANIZER ZIP INSPECTION"
}
catch {
  Write-Host ""
  Write-Host "INSTALL FAILED - restoring Phase 1.1 baseline."
  Restore-Backup
  throw
}
