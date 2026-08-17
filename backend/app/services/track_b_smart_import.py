from __future__ import annotations
import hashlib, io, json, re, shutil, subprocess, tempfile, zipfile
from pathlib import Path
from typing import Any
from fastapi import UploadFile
from app.core.config import get_settings
from app.services.track_b import TrackBError
from app.services.track_b_smart_intake import inspect_organizer_package

# SMART_ORGANIZER_PHASE2A
_GIS_EXTENSIONS={".tab",".dat",".map",".id",".ind",".shp",".shx",".dbf",".prj",".cpg",".qix",".gpkg"}
_MAPINFO_REQUIRED={".tab",".dat",".map",".id"}
_SHAPEFILE_REQUIRED={".shp",".shx",".dbf"}
_SAFE_NAME=re.compile(r"[^A-Za-z0-9_.-]+")

def _safe_basename(name:str)->str:
    return _SAFE_NAME.sub("_",Path(name).name)[:180] or "dataset"

def _run(cmd:list[str])->subprocess.CompletedProcess[str]:
    return subprocess.run(cmd,check=False,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=120)

def _ogr_available()->bool:
    return shutil.which("ogr2ogr") is not None and shutil.which("ogrinfo") is not None

def _feature_summary(path:Path)->dict[str,Any]:
    payload=json.loads(path.read_text(encoding="utf-8"))
    features=payload.get("features") or []
    types=sorted({str((f.get("geometry") or {}).get("type")) for f in features if isinstance(f,dict) and (f.get("geometry") or {}).get("type")})
    return {"feature_count":len(features),"geometry_types":types,"geojson":payload}

def _list_gpkg_layers(path:Path)->list[str]:
    r=_run(["ogrinfo","-ro","-q",str(path)])
    if r.returncode!=0: raise TrackBError(f"GDAL could not inspect GeoPackage: {r.stderr.strip()}")
    out=[]
    for line in r.stdout.splitlines():
        m=re.match(r"^\s*\d+\s*:\s*(.+?)(?:\s+\(.+\))?\s*$",line)
        if m: out.append(m.group(1).strip())
    return out

def _convert_one(source:Path,output:Path,layer_name:str|None=None)->dict[str,Any]:
    cmd=["ogr2ogr","-f","GeoJSON","-t_srs","EPSG:4326",str(output),str(source)]
    if layer_name: cmd.append(layer_name)
    r=_run(cmd)
    if r.returncode!=0: raise TrackBError(f"GDAL conversion failed for {source.name}: {r.stderr.strip()}")
    s=_feature_summary(output)
    return {"source_name":source.name,"source_layer":layer_name,"source_format":source.suffix.casefold(),"normalized_crs":"EPSG:4326","feature_count":s["feature_count"],"geometry_types":s["geometry_types"],"geojson":s["geojson"]}

def _extract_zip_safely(data:bytes,root:Path)->list[Path]:
    out=[]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for info in z.infolist():
            if info.is_dir(): continue
            member=info.filename.replace("\\","/")
            parts=[p for p in member.split("/") if p not in {"","."}]
            if ".." in parts or member.startswith("/"): continue
            if Path(member).suffix.casefold() not in _GIS_EXTENSIONS: continue
            d=root.joinpath(*parts[:-1]); d.mkdir(parents=True,exist_ok=True)
            target=d/_safe_basename(parts[-1]); target.write_bytes(z.read(info)); out.append(target)
    return out

def _bundle_key(path:Path,root:Path)->tuple[str,str]:
    rel=path.relative_to(root)
    return (str(rel.parent).casefold(),rel.stem.casefold())

async def prepare_import_plan(files:list[UploadFile])->dict[str,Any]:
    if not files: raise TrackBError("Phase 2A requires at least one organizer file.")
    if not _ogr_available(): raise TrackBError("GDAL ogr2ogr/ogrinfo is unavailable in backend runtime.")
    limit=max(int(get_settings().raster_upload_max_bytes),int(get_settings().document_upload_max_bytes))
    raw=[]; inspection_files=[]
    for upload in files:
        data=await upload.read(limit+1)
        if len(data)>limit: raise TrackBError(f"Organizer file exceeds configured limit: {upload.filename}")
        raw.append((upload.filename or "upload",data))
        inspection_files.append(UploadFile(filename=upload.filename,file=io.BytesIO(data)))
    inspection=await inspect_organizer_package(inspection_files)
    normalized=[]; limitations=[]
    with tempfile.TemporaryDirectory(prefix="geopilot-smart-import-") as tmp:
        root=Path(tmp); extracted=[]
        for name,data in raw:
            suffix=Path(name).suffix.casefold()
            if suffix==".zip": extracted.extend(_extract_zip_safely(data,root))
            elif suffix in _GIS_EXTENSIONS:
                p=root/_safe_basename(name); p.write_bytes(data); extracted.append(p)
        groups={}; gpkg=[]
        for p in extracted:
            if p.suffix.casefold()==".gpkg": gpkg.append(p)
            else: groups.setdefault(_bundle_key(p,root),[]).append(p)
        for (_parent,_stem),members in sorted(groups.items()):
            suffixes={p.suffix.casefold() for p in members}; source=None; fmt=None; missing=[]
            if ".tab" in suffixes or suffixes & {".dat",".map",".id",".ind"}:
                fmt="mapinfo_tab"; missing=sorted(_MAPINFO_REQUIRED-suffixes); source=next((p for p in members if p.suffix.casefold()==".tab"),None)
            elif ".shp" in suffixes or suffixes & {".shx",".dbf",".prj",".cpg",".qix"}:
                fmt="esri_shapefile"; missing=sorted(_SHAPEFILE_REQUIRED-suffixes); source=next((p for p in members if p.suffix.casefold()==".shp"),None)
            if not fmt: continue
            if missing or source is None:
                limitations.append(f"{members[0].stem}: incomplete {fmt} bundle; missing {', '.join(missing)}."); continue
            out=root/f"normalized_{len(normalized)}.geojson"; c=_convert_one(source,out)
            normalized.append({"logical_name":source.stem,"format":fmt,"source_members":[str(p.relative_to(root)) for p in members],"source_checksum_sha256":hashlib.sha256(b"".join(p.read_bytes() for p in sorted(members))).hexdigest(),"requires_confirmation":True,"suggested_role":None,"normalized":c})
        for p in gpkg:
            layers=_list_gpkg_layers(p)
            if not layers: limitations.append(f"{p.name}: GeoPackage contains no readable layers."); continue
            for layer in layers:
                out=root/f"normalized_{len(normalized)}.geojson"; c=_convert_one(p,out,layer)
                normalized.append({"logical_name":f"{p.stem}:{layer}","format":"geopackage","source_members":[str(p.relative_to(root))],"source_checksum_sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"requires_confirmation":True,"suggested_role":None,"normalized":c})
    return {"phase":"phase2a_prepare_only","database_writes":False,"migration_required":False,"inspection":inspection,"normalized_dataset_count":len(normalized),"normalized_datasets":normalized,"limitations":limitations,"next_action":"Confirm each logical GIS dataset role and Site/project assignment before persistent Import All."}
