from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from fastapi import UploadFile
from app.core.config import get_settings
from app.services.track_b import TrackBError, _infer_acquisition_datetime, _inspect_bytes

# SMART_ORGANIZER_INTAKE_V1
_SENTINEL_BAND_RE = re.compile(r"(?:^|[_\-.])(B02|B03|B04|B08|B11|SCL)(?:[_\-.]|$)", re.I)
_LOCATION = (("urban", ("urban","bandar","city","metro")), ("rural", ("rural","luar_bandar","luar-bandar","luar bandar","kampung")))
_BEFORE = ("t1","before","pre_","pre-","awal","baseline")
_AFTER = ("t2","after","post_","post-","akhir","followup","follow-up")
_REFERENCE = ("reference","ref_","ref-","rujukan")
_PROCESSED = ("processed","classif","classification","change_mask","change-mask","ndvi","ndwi","ndbi","index","derived")
_DEM = ("dem","elevation","elevasi","height","dtm","dsm")
_ROLES = (
    ("planning_subzone", ("subzone","sub_zone","sub-zone","subzon")),
    ("planning_block", ("planning_block","planning-block","planning block","bpk","blok_perancangan")),
    ("land_use", ("landuse","land_use","land-use","guna_tanah","guna-tanah","guna tanah")),
    ("zoning", ("zoning","zone","zon")),
)

def _norm(v: str | None) -> str:
    return (v or "").replace("\\","/").casefold()

def _first_rule(name: str, rules):
    for value, terms in rules:
        if any(term in name for term in terms):
            return value
    return None

def _temporal(name: str):
    if any(x in name for x in _BEFORE): return "before"
    if any(x in name for x in _AFTER): return "after"
    if any(x in name for x in _REFERENCE): return "reference"
    return None

def _stage(name: str, raster_like: bool):
    if any(x in name for x in _PROCESSED): return "processed"
    return "raw" if raster_like else None

def _band(name: str):
    m = _SENTINEL_BAND_RE.search(Path(name).name)
    return m.group(1).upper() if m else None

def _base(upload: UploadFile, i: int) -> dict[str, Any]:
    filename = upload.filename or f"file_{i}"
    n = _norm(filename)
    return {
        "index": i, "filename": filename, "extension": Path(filename).suffix.casefold(),
        "content_type": upload.content_type, "size_bytes": 0, "classification": "unsupported",
        "confidence": "low", "location_type": _first_rule(n, _LOCATION),
        "temporal_role": _temporal(n), "data_stage": None, "band_name": _band(n),
        "acquisition_datetime": _infer_acquisition_datetime(filename),
        "suggested_applicability_role": _first_rule(n, _ROLES),
        "requires_confirmation": True, "metadata": {}, "issues": [],
    }

def _geojson(item, data: bytes):
    try:
        payload = json.loads(data.decode("utf-8-sig"))
    except Exception:
        item["classification"]="invalid_geojson"; item["confidence"]="high"
        item["issues"].append("GeoJSON/JSON content is not valid UTF-8 JSON."); return
    if not isinstance(payload, dict) or payload.get("type")!="FeatureCollection":
        item["classification"]="geojson_non_feature_collection"; item["confidence"]="high"
        item["issues"].append("Planning spatial import requires a GeoJSON FeatureCollection."); return
    features = payload.get("features")
    if not isinstance(features, list):
        item["classification"]="invalid_geojson"; item["confidence"]="high"
        item["issues"].append("FeatureCollection has no valid features array."); return
    types = sorted({str((f.get("geometry") or {}).get("type")) for f in features if isinstance(f,dict) and (f.get("geometry") or {}).get("type")})
    item["metadata"]={"feature_count":len(features),"geometry_types":types,"source_crs_assumption":"EPSG:4326 V1 contract"}
    if types and all(t in {"Polygon","MultiPolygon"} for t in types):
        item["classification"]="planning_spatial_candidate"; item["confidence"]="high"; item["requires_confirmation"]=True
        if not item["suggested_applicability_role"]:
            item["issues"].append("Choose zoning, land_use, planning_block, or planning_subzone before import.")
        item["issues"].append("Confirm authority, jurisdiction, source title, and EPSG:4326 before import.")
    else:
        item["classification"]="geojson_vector_candidate"; item["confidence"]="moderate"; item["requires_confirmation"]=True
        item["issues"].append("Current planning applicability importer accepts Polygon/MultiPolygon only.")

def _archive(item, data: bytes):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            members=[m.filename for m in z.infolist() if not m.is_dir()]
    except Exception:
        item["classification"]="invalid_archive"; item["confidence"]="high"; item["issues"].append("ZIP is not readable."); return
    bands=sorted({m.group(1).upper() for name in members for m in [_SENTINEL_BAND_RE.search(Path(name).name)] if m})
    item["metadata"]={"member_count":len(members),"sentinel_bands_detected":bands}
    item["data_stage"]=_stage(_norm(item["filename"]), True)
    if bands:
        item["classification"]="sentinel_archive_candidate"; item["confidence"]="high"
        item["requires_confirmation"]=not (item["location_type"] and item["temporal_role"])
        if not item["location_type"]: item["issues"].append("Urban/Rural could not be inferred.")
        if not item["temporal_role"]: item["issues"].append("T1/T2 could not be inferred.")
    else:
        item["classification"]="archive_unknown"; item["confidence"]="moderate"; item["requires_confirmation"]=True
        item["issues"].append("No supported Sentinel band names B02/B03/B04/B08/B11/SCL were detected.")

async def inspect_organizer_package(files: list[UploadFile]) -> dict[str, Any]:
    if not files: raise TrackBError("Organizer package inspection requires at least one file.")
    s=get_settings()
    per_file=max(int(s.raster_upload_max_bytes), int(s.document_upload_max_bytes))
    total_limit=per_file*4
    total=0; items=[]
    for i, upload in enumerate(files):
        item=_base(upload,i)
        data=await upload.read(per_file+1)
        item["size_bytes"]=len(data)
        if not data:
            item["classification"]="empty"; item["confidence"]="high"; item["issues"].append("File is empty."); items.append(item); continue
        if len(data)>per_file:
            item["classification"]="too_large"; item["confidence"]="high"; item["issues"].append("File exceeds configured inspection limit."); items.append(item); continue
        total += len(data)
        if total > total_limit: raise TrackBError("Organizer package exceeds aggregate Smart Intake inspection limit.")
        suffix=item["extension"]; n=_norm(item["filename"])
        if suffix in {".tif",".tiff",".jp2"}:
            item["data_stage"]=_stage(n, True)
            try:
                r=_inspect_bytes(data)
                item["metadata"]={"crs":r.crs,"width":r.width,"height":r.height,"band_count":r.count,"band_names":r.band_names,"pixel_size":r.pixel_size,"bounds":r.bounds,"driver":r.driver,"dtype":r.dtype}
                if any(x in n for x in _DEM) and r.count==1:
                    item["classification"]="terrain_dem_candidate"; item["confidence"]="high"; item["requires_confirmation"]=True
                    item["issues"].append("DEM candidate requires Site assignment and Terrain Engine validation.")
                elif item["band_name"] and r.count==1:
                    item["classification"]="raster_band_candidate"; item["confidence"]="high"; item["requires_confirmation"]=not(item["location_type"] and item["temporal_role"])
                else:
                    item["classification"]="raster_dataset_candidate"; item["confidence"]="high"; item["requires_confirmation"]=not(item["location_type"] and item["temporal_role"])
                if item["classification"]!="terrain_dem_candidate":
                    if not item["location_type"]: item["issues"].append("Urban/Rural could not be inferred.")
                    if not item["temporal_role"]: item["issues"].append("T1/T2 could not be inferred.")
            except Exception as exc:
                item["classification"]="invalid_raster"; item["confidence"]="high"; item["issues"].append(str(exc))
        elif suffix==".zip": _archive(item,data)
        elif suffix in {".geojson",".json"}: _geojson(item,data)
        elif suffix==".pdf":
            item["classification"]="planning_document_candidate"; item["confidence"]="high"; item["requires_confirmation"]=True
            item["metadata"]={"document_class_required":True}
            item["issues"].append("Confirm RFN/RSN/RT/RKK/GPP/other class and registration metadata before import.")
        elif suffix==".csv":
            try:
                header=next(csv.reader(io.StringIO(data.decode("utf-8-sig"))),[])
            except Exception: header=[]
            item["classification"]="metadata_helper"; item["confidence"]="high"; item["requires_confirmation"]=False
            item["metadata"]={"columns":header[:50]}
            item["issues"].append("CSV is helper metadata only in Smart Intake V1.")
        else:
            item["classification"]="unsupported"; item["confidence"]="high"; item["requires_confirmation"]=False
            item["issues"].append(f"Unsupported Smart Intake V1 extension: {suffix or 'none'}.")
        items.append(item)
    counts={}
    for x in items: counts[x["classification"]]=counts.get(x["classification"],0)+1
    blockers=[x["filename"] for x in items if x["classification"] in {"empty","too_large","invalid_raster","invalid_geojson","invalid_archive"}]
    return {
        "phase":"inspect_only","database_writes":False,"file_count":len(items),
        "supported_or_reviewable_count":sum(x["classification"] not in {"unsupported","empty","too_large"} for x in items),
        "requires_confirmation_count":sum(bool(x["requires_confirmation"]) for x in items),
        "blocker_count":len(blockers),"class_counts":counts,"blockers":blockers,"items":items,
        "next_action":"Review classifications and required confirmations before Import All."
    }


# SMART_ORGANIZER_ZIP_V1_2_2
_ZIP_SUPPORTED_SUFFIXES = {".tif", ".tiff", ".jp2", ".zip", ".geojson", ".json", ".pdf", ".csv", ".tab", ".dat", ".map", ".id", ".ind", ".shp", ".shx", ".dbf", ".prj", ".cpg", ".qix", ".gpkg", ".qmd"}
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

    # SMART_ORGANIZER_GIS_BUNDLE_V1_3
    # Recognize multi-file vector datasets as ONE logical organizer dataset.
    # This phase is inspect-only: it does not parse geometry, transform CRS,
    # create GIS layers/features, or write to the database.
    _mapinfo_required = {".tab", ".dat", ".map", ".id"}
    _mapinfo_optional = {".ind"}
    _shapefile_required = {".shp", ".shx", ".dbf"}
    _shapefile_optional = {".prj", ".cpg", ".qix"}
    _gis_sidecars = _mapinfo_required | _mapinfo_optional | _shapefile_required | _shapefile_optional

    def _bundle_key(item):
        archive_path = (item.get("archive_path") or item.get("filename") or "").replace("\\", "/")
        p = Path(archive_path)
        parent = str(p.parent).casefold()
        stem = p.stem.casefold()
        source_archive = (item.get("source_archive") or "").casefold()
        return (source_archive, parent, stem)

    bundle_members = {}
    for item in expanded:
        suffix = (item.get("extension") or "").casefold()
        if suffix in _gis_sidecars:
            bundle_members.setdefault(_bundle_key(item), []).append(item)

    gis_bundles = []
    for key, members in bundle_members.items():
        suffixes = {(x.get("extension") or "").casefold() for x in members}
        member_names = [x.get("archive_path") or x.get("filename") for x in members]

        if ".tab" in suffixes or bool(suffixes & {".dat", ".map", ".id"}):
            fmt = "mapinfo_tab"
            required = _mapinfo_required
            classification = "gis_mapinfo_bundle_candidate"
        else:
            fmt = "esri_shapefile"
            required = _shapefile_required
            classification = "gis_shapefile_bundle_candidate"

        missing = sorted(required - suffixes)
        complete = not missing
        primary_suffix = ".tab" if fmt == "mapinfo_tab" else ".shp"
        primary = next((x for x in members if (x.get("extension") or "").casefold() == primary_suffix), members[0])

        for item in members:
            item["classification"] = classification if complete else "gis_bundle_incomplete"
            item["confidence"] = "high"
            item["requires_confirmation"] = True
            item["metadata"] = {
                **(item.get("metadata") or {}),
                "logical_gis_bundle": True,
                "gis_format": fmt,
                "bundle_complete": complete,
                "bundle_members": member_names,
                "missing_required_extensions": missing,
                "primary_member": primary.get("archive_path") or primary.get("filename"),
                "geometry_not_parsed": True,
                "database_writes": False,
            }
            item["issues"] = [
                (
                    f"Recognized complete {fmt} GIS bundle. Confirm layer role, CRS and Site/project assignment before import."
                    if complete
                    else f"Incomplete {fmt} GIS bundle; missing required members: {', '.join(missing)}."
                )
            ]

        gis_bundles.append({
            "format": fmt,
            "classification": classification if complete else "gis_bundle_incomplete",
            "complete": complete,
            "members": member_names,
            "missing_required_extensions": missing,
            "primary_member": primary.get("archive_path") or primary.get("filename"),
            "requires_confirmation": True,
        })

    # SMART_ORGANIZER_FORMAT_COVERAGE_V1_3_3
    # Inspection-only format coverage. No GIS parsing/conversion and no DB writes.
    for item in expanded:
        suffix = (item.get("extension") or "").casefold()

        if suffix == ".gpkg":
            item["classification"] = "gis_geopackage_candidate"
            item["confidence"] = "high"
            item["requires_confirmation"] = True
            item["metadata"] = {
                **(item.get("metadata") or {}),
                "gis_format": "geopackage",
                "geometry_not_parsed": True,
                "database_writes": False,
            }
            item["issues"] = [
                "Recognized GeoPackage GIS dataset. Confirm layer role, CRS and Site/project assignment before import."
            ]

        elif suffix == ".qmd":
            item["classification"] = "organizer_auxiliary_ignored"
            item["confidence"] = "high"
            item["requires_confirmation"] = False
            item["metadata"] = {
                **(item.get("metadata") or {}),
                "auxiliary_only": True,
                "database_writes": False,
            }
            item["issues"] = [
                "Recognized auxiliary QMD member. It is safely ignored for spatial import."
            ]

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
        "gis_bundle_recognition": True,
        "gis_bundle_count": len(gis_bundles),
        "gis_bundles": gis_bundles,
    }


