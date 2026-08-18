$ErrorActionPreference = "Stop"
Write-Host "============================================================"
Write-Host "GeoPilot Smart Organizer ZIP V1.2.1"
Write-Host "Import repair + recursive ZIP inspection"
Write-Host "NO DB WRITE / NO MIGRATION"
Write-Host "============================================================"

$root=(Get-Location).Path
$stamp=Get-Date -Format "yyyyMMdd_HHmmss"
$backup=Join-Path $root "artifacts\smart_organizer_zip_v1_2_1_backup_$stamp"
$service=Join-Path $root "backend\app\services\track_b_smart_intake.py"
$test=Join-Path $root "backend\tests\test_track_b_smart_organizer_zip_v1_2_1.py"

if(-not (Test-Path $service)){throw "Phase 1.1 service not found."}
New-Item -ItemType Directory -Force $backup | Out-Null
Copy-Item $service (Join-Path $backup "track_b_smart_intake.py") -Force

function Restore-Backup {
  Copy-Item (Join-Path $backup "track_b_smart_intake.py") $service -Force
  if(Test-Path $test){Remove-Item $test -Force}
}

try {
  Write-Host "BACKUP: $backup"
  Write-Host "[0] Baseline + rollback gate"
  $t=Get-Content $service -Raw
  if(-not $t.Contains("inspect_organizer_package")){throw "Phase 1.1 baseline missing."}
  if($t.Contains("SMART_ORGANIZER_ZIP_V1_2")){throw "Old V1.2 patch still present; expected rollback state."}
  Write-Host "phase1_1_baseline=CONFIRMED"

  Write-Host "[1] Patch required standard-library imports"
  # Exact root cause from probe: V1.2 used Path/zipfile/io in runtime patch without importing them.
  $patched=$t
  if($patched -notmatch "(?m)^import io\s*$"){
    $patched=$patched -replace "from __future__ import annotations\r?\n", "from __future__ import annotations`r`n`r`nimport io`r`nimport zipfile`r`nfrom pathlib import Path`r`n"
  } else {
    if($patched -notmatch "(?m)^import zipfile\s*$"){ $patched=$patched -replace "(?m)^import io\s*$", "import io`r`nimport zipfile" }
    if($patched -notmatch "(?m)^from pathlib import Path\s*$"){ $patched=$patched -replace "(?m)^import zipfile\s*$", "import zipfile`r`nfrom pathlib import Path" }
  }
  Set-Content $service $patched -Encoding UTF8

  Write-Host "[2] Append corrected V1.2 ZIP implementation"
  @'

# SMART_ORGANIZER_ZIP_V1_2_1
_ZIP_SUPPORTED_SUFFIXES = {".tif", ".tiff", ".jp2", ".zip", ".geojson", ".json", ".pdf", ".csv"}
_ZIP_MAX_MEMBERS = 1000
_ZIP_MAX_DEPTH = 2

def _zip_member_item(member_name: str, data: bytes, index: int, archive_name: str) -> dict[str, Any]:
    class _MemberUpload:
        filename = member_name
        content_type = None
    item = _base_item(_MemberUpload(), index)
    item["archive_path"] = member_name
    item["source_archive"] = archive_name
    item["size_bytes"] = len(data)
    suffix = item["extension"]
    normalized = _norm(member_name)
    if suffix in {".tif", ".tiff", ".jp2"}:
        item["data_stage"] = _infer_stage(normalized, raster_like=True)
        try:
            inspected = _inspect_bytes(data)
            item["metadata"] = {"crs": inspected.crs, "width": inspected.width, "height": inspected.height,
                "band_count": inspected.count, "band_names": inspected.band_names, "pixel_size": inspected.pixel_size,
                "bounds": inspected.bounds, "driver": inspected.driver, "dtype": inspected.dtype}
            dem_hint = any(term in normalized for term in _DEM_TERMS)
            if dem_hint and inspected.count == 1:
                item["classification"]="terrain_dem_candidate"; item["confidence"]="high"; item["requires_confirmation"]=True
                item["issues"].append("DEM candidate requires Site assignment and Terrain Engine validation before import.")
            elif item["band_name"] is not None and inspected.count == 1:
                item["classification"]="raster_band_candidate"; item["confidence"]="high"
                item["requires_confirmation"]=item["location_type"] is None or item["temporal_role"] is None
            else:
                item["classification"]="raster_dataset_candidate"; item["confidence"]="high"
                item["requires_confirmation"]=item["location_type"] is None or item["temporal_role"] is None
        except Exception as exc:
            item["classification"]="invalid_raster"; item["confidence"]="high"; item["requires_confirmation"]=True
            item["issues"].append(str(exc))
    elif suffix in {".geojson", ".json"}:
        _inspect_geojson(item, data)
    elif suffix == ".pdf":
        item["classification"]="planning_document_candidate"; item["confidence"]="high"; item["requires_confirmation"]=True
        item["metadata"]={"document_class_required": True}
        item["issues"].append("Confirm RFN/RSN/RT/RKK/GPP/other document class and registration metadata before import.")
    elif suffix == ".csv":
        _inspect_csv(item, data)
    else:
        item["classification"]="unsupported"; item["confidence"]="high"; item["requires_confirmation"]=False
        item["issues"].append(f"Archive member '{suffix or 'no-extension'}' is not supported by Smart Intake V1.2.1.")
    return item

def _inspect_zip_members(archive_name: str, data: bytes, *, depth: int=0, start_index: int=0) -> list[dict[str, Any]]:
    if depth > _ZIP_MAX_DEPTH:
        return [{"index":start_index,"filename":archive_name,"archive_path":archive_name,"source_archive":archive_name,
          "extension":".zip","content_type":None,"size_bytes":len(data),"classification":"archive_depth_blocked",
          "confidence":"high","location_type":None,"temporal_role":None,"data_stage":None,"band_name":None,
          "acquisition_datetime":None,"suggested_applicability_role":None,"requires_confirmation":True,"metadata":{},
          "issues":["Nested ZIP depth exceeds Smart Intake safety limit."]}]
    try:
        archive=zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, RuntimeError):
        return [{"index":start_index,"filename":archive_name,"archive_path":archive_name,"source_archive":archive_name,
          "extension":".zip","content_type":None,"size_bytes":len(data),"classification":"invalid_archive",
          "confidence":"high","location_type":None,"temporal_role":None,"data_stage":None,"band_name":None,
          "acquisition_datetime":None,"suggested_applicability_role":None,"requires_confirmation":True,"metadata":{},
          "issues":["ZIP file is not a readable archive."]}]
    infos=[x for x in archive.infolist() if not x.is_dir()]
    if len(infos)>_ZIP_MAX_MEMBERS: raise TrackBError(f"Organizer ZIP contains more than {_ZIP_MAX_MEMBERS} files.")
    results=[]; index=start_index
    for info in infos:
        member=info.filename.replace("\\","/")
        parts=[x for x in member.split("/") if x not in {"","."}]
        if ".." in parts or member.startswith("/"):
            results.append({"index":index,"filename":member,"archive_path":member,"source_archive":archive_name,
              "extension":Path(member).suffix.casefold(),"content_type":None,"size_bytes":int(info.file_size),
              "classification":"unsafe_archive_path","confidence":"high","location_type":_infer_location(_norm(member)),
              "temporal_role":_infer_temporal_role(_norm(member)),"data_stage":None,"band_name":_infer_band(_norm(member)),
              "acquisition_datetime":_infer_acquisition_datetime(member),"suggested_applicability_role":_infer_planning_role(_norm(member)),
              "requires_confirmation":True,"metadata":{},"issues":["Unsafe archive path was blocked; no extraction occurred."]})
            index+=1; continue
        suffix=Path(member).suffix.casefold()
        if suffix not in _ZIP_SUPPORTED_SUFFIXES:
            results.append(_zip_member_item(member,b"",index,archive_name)); index+=1; continue
        limit=max(int(get_settings().raster_upload_max_bytes),int(get_settings().document_upload_max_bytes))
        if info.file_size>limit:
            results.append({"index":index,"filename":member,"archive_path":member,"source_archive":archive_name,
              "extension":suffix,"content_type":None,"size_bytes":int(info.file_size),"classification":"too_large",
              "confidence":"high","location_type":_infer_location(_norm(member)),"temporal_role":_infer_temporal_role(_norm(member)),
              "data_stage":None,"band_name":_infer_band(_norm(member)),"acquisition_datetime":_infer_acquisition_datetime(member),
              "suggested_applicability_role":_infer_planning_role(_norm(member)),"requires_confirmation":True,"metadata":{},
              "issues":["Archive member exceeds configured Smart Intake per-file limit."]})
            index+=1; continue
        member_data=archive.read(info)
        if suffix==".zip":
            nested=_inspect_zip_members(f"{archive_name}:{member}",member_data,depth=depth+1,start_index=index)
            results.extend(nested); index+=max(1,len(nested))
        else:
            results.append(_zip_member_item(member,member_data,index,archive_name)); index+=1
    return results

_inspect_organizer_package_v1_1 = inspect_organizer_package

async def inspect_organizer_package(files: list[UploadFile]) -> dict[str, Any]:
    if not files: raise TrackBError("Organizer package inspection requires at least one file.")
    expanded=[]; ordinary=[]
    for upload in files:
        if Path(upload.filename or "").suffix.casefold()!=".zip":
            ordinary.append(upload); continue
        limit=max(int(get_settings().raster_upload_max_bytes),int(get_settings().document_upload_max_bytes))
        data=await upload.read(limit+1)
        if len(data)>limit:
            expanded.append({"index":len(expanded),"filename":upload.filename or "archive.zip","archive_path":upload.filename or "archive.zip",
              "source_archive":upload.filename or "archive.zip","extension":".zip","content_type":upload.content_type,"size_bytes":len(data),
              "classification":"too_large","confidence":"high","location_type":None,"temporal_role":None,"data_stage":None,"band_name":None,
              "acquisition_datetime":None,"suggested_applicability_role":None,"requires_confirmation":True,"metadata":{},
              "issues":["Organizer ZIP exceeds configured Smart Intake inspection limit."]})
        else:
            expanded.extend(_inspect_zip_members(upload.filename or "archive.zip",data,start_index=len(expanded)))
    if ordinary:
        base=await _inspect_organizer_package_v1_1(ordinary)
        for item in base["items"]:
            item["index"]=len(expanded); item["archive_path"]=None; item["source_archive"]=None; expanded.append(item)
    counts={}
    for item in expanded: counts[item["classification"]]=counts.get(item["classification"],0)+1
    blocker_classes={"empty","too_large","invalid_raster","invalid_geojson","invalid_archive","unsafe_archive_path","archive_depth_blocked"}
    blockers=[x["filename"] for x in expanded if x["classification"] in blocker_classes]
    return {"phase":"inspect_only","database_writes":False,"file_count":len(expanded),
      "supported_or_reviewable_count":sum(x["classification"] not in {"unsupported","empty","too_large"} for x in expanded),
      "requires_confirmation_count":sum(bool(x["requires_confirmation"]) for x in expanded),
      "blocker_count":len(blockers),"class_counts":counts,"blockers":blockers,"items":expanded,
      "next_action":"Review ZIP contents and classifications before Import All.","archive_expansion":True}
'@ | Add-Content $service -Encoding UTF8

  Write-Host "[3] Install focused regression"
  @'
from __future__ import annotations
import asyncio, io, json, zipfile
from fastapi import UploadFile
from app.services.track_b_smart_intake import inspect_organizer_package
def up(n,d): return UploadFile(filename=n,file=io.BytesIO(d))
def run(f): return asyncio.run(inspect_organizer_package(f))
def z(entries):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w",zipfile.ZIP_DEFLATED) as a:
        for n,d in entries.items(): a.writestr(n,d)
    return b.getvalue()
def test_mixed():
    g=json.dumps({"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":{"type":"Polygon","coordinates":[[[101,3],[101.1,3],[101.1,3.1],[101,3]]]}}]}).encode()
    r=run([up("Organizer.zip",z({"Urban/Planning/urban_zoning.geojson":g,"Documents/RT.pdf":b"%PDF-1.4","metadata.csv":b"name,date\nx,y\n","notes.xyz":b"x"}))])
    c={x["classification"] for x in r["items"]}
    assert r["archive_expansion"] and not r["database_writes"]
    assert {"planning_spatial_candidate","planning_document_candidate","metadata_helper","unsupported"}<=c
def test_hints():
    r=run([up("Organizer.zip",z({"Urban/T1/urban_T1_B04.jp2":b"bad"}))]); x=r["items"][0]
    assert x["location_type"]=="urban" and x["temporal_role"]=="before" and x["band_name"]=="B04"
def test_zip_slip():
    r=run([up("Organizer.zip",z({"../evil.pdf":b"x"}))])
    assert r["items"][0]["classification"]=="unsafe_archive_path"
def test_nested():
    r=run([up("Organizer.zip",z({"nested/materials.zip":z({"Documents/GPP.pdf":b"%PDF-1.4"})}))])
    assert any(x["classification"]=="planning_document_candidate" for x in r["items"])
'@ | Set-Content $test -Encoding UTF8

  Write-Host "[4] Syntax"
  docker compose exec -T backend python -m py_compile /app/app/services/track_b_smart_intake.py
  if($LASTEXITCODE-ne 0){throw "Syntax failed."}

  Write-Host "[5] Phase 1.1 regression"
  docker compose exec -T backend python -m pytest -q tests/test_track_b_smart_organizer_intake_v1.py
  if($LASTEXITCODE-ne 0){throw "Phase 1.1 regression failed."}

  Write-Host "[6] ZIP V1.2.1 regression"
  docker compose exec -T backend python -m pytest -q tests/test_track_b_smart_organizer_zip_v1_2_1.py
  if($LASTEXITCODE-ne 0){throw "ZIP regression failed."}

  Write-Host "[7] Full backend regression"
  docker compose exec -T backend python -m pytest -q
  if($LASTEXITCODE-ne 0){throw "Full backend regression failed."}

  Write-Host "[8] Frontend typecheck/build"
  docker compose exec -T frontend npm run typecheck
  if($LASTEXITCODE-ne 0){throw "Frontend typecheck failed."}
  docker compose exec -T frontend npm run build
  if($LASTEXITCODE-ne 0){throw "Frontend build failed."}

  Write-Host "[9] Recreate backend"
  docker compose up -d --force-recreate backend
  if($LASTEXITCODE-ne 0){throw "Backend recreate failed."}
  Start-Sleep -Seconds 8
  docker compose ps backend

  Write-Host "[10] Runtime verification"
  docker compose exec -T backend python -c "from pathlib import Path; t=Path('/app/app/services/track_b_smart_intake.py').read_text(); assert 'SMART_ORGANIZER_ZIP_V1_2_1' in t; import app.services.track_b_smart_intake as m; assert hasattr(m,'_inspect_zip_members'); print('runtime_zip_v1_2_1=PASS')"
  if($LASTEXITCODE-ne 0){throw "Runtime verification failed."}

  Write-Host "============================================================"
  Write-Host "SMART ORGANIZER ZIP V1.2.1 PASS"
  Write-Host "============================================================"
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
