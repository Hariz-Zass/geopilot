from __future__ import annotations
import io
from typing import Any
from fastapi import UploadFile
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from app.core.config import get_settings
from app.services.track_b import TrackBError
from app.services.track_b_smart_import import prepare_import_plan

# SMART_ORGANIZER_PHASE2B2_SITE_DISCOVERY
_SITE_HINTS=("semp_tapak","semp tapak","sempadan tapak","site_boundary","site boundary","boundary","tapak","kawasan kajian","study area","project area")
_NON_SITE_HINTS=("lot","parcel","cadastre","cadastral","jalan","road","network","rangkaian")
_MAX_AUTO_REVIEW_FEATURES=100

def _score(name:str)->int:
    n=name.casefold().replace("-"," ").replace("_"," ")
    s=5 if any(h.replace("_"," ") in n for h in _SITE_HINTS) else 0
    if any(h in n for h in _NON_SITE_HINTS): s-=5
    return s

def _candidate(dataset:dict[str,Any])->dict[str,Any]:
    norm=dataset.get("normalized") or {}
    name=str(dataset.get("logical_name") or "")
    count=int(norm.get("feature_count") or 0)
    features=(norm.get("geojson") or {}).get("features") or []
    polys=[f for f in features if isinstance(f,dict) and (f.get("geometry") or {}).get("type") in {"Polygon","MultiPolygon"}]
    out={"logical_name":name,"format":dataset.get("format"),"source_checksum_sha256":dataset.get("source_checksum_sha256"),"normalized_crs":norm.get("normalized_crs"),"feature_count":count,"geometry_types":list(norm.get("geometry_types") or []),"candidate_status":"not_site_candidate","requires_confirmation":False,"reasons":[],"bounds":None,"union_geometry":None}
    if count==0:
        out["candidate_status"]="empty_boundary_candidate"; out["requires_confirmation"]=True
        out["reasons"].append("Dataset contains no usable polygon features.")
        return out
    if not polys:
        out["reasons"].append("No Polygon/MultiPolygon geometry.")
        return out
    if count>_MAX_AUTO_REVIEW_FEATURES:
        out["candidate_status"]="large_polygon_reference_layer"
        out["reasons"].append("Too many polygon features to treat automatically as one competition Site boundary.")
        return out
    geoms=[]
    for f in polys:
        try:
            g=shape(f["geometry"])
            if not g.is_empty and g.is_valid: geoms.append(g)
        except Exception:
            pass
    if not geoms:
        out["candidate_status"]="invalid_boundary_candidate"; out["requires_confirmation"]=True
        out["reasons"].append("No valid polygon geometry available.")
        return out
    merged=unary_union(geoms)
    score=_score(name)+(3 if len(geoms)==1 else 1 if len(geoms)<=10 else 0)
    out["bounds"]=list(merged.bounds); out["union_geometry"]=mapping(merged); out["requires_confirmation"]=True
    out["candidate_status"]="strong_site_boundary_candidate" if score>=5 else "review_site_boundary_candidate"
    out["reasons"].append("Organizer polygon requires user confirmation before Site creation.")
    return out

async def discover_site_candidates(files:list[UploadFile])->dict[str,Any]:
    if not files: raise TrackBError("Organizer Site discovery requires at least one file.")
    limit=max(int(get_settings().raster_upload_max_bytes),int(get_settings().document_upload_max_bytes))
    cloned=[]
    for upload in files:
        data=await upload.read(limit+1)
        if len(data)>limit: raise TrackBError(f"Organizer file exceeds configured limit: {upload.filename}")
        cloned.append(UploadFile(filename=upload.filename,file=io.BytesIO(data)))
    plan=await prepare_import_plan(cloned)
    candidates=[_candidate(d) for d in plan.get("normalized_datasets",[])]
    strong=[c for c in candidates if c["candidate_status"]=="strong_site_boundary_candidate"]
    review=[c for c in candidates if c["candidate_status"]=="review_site_boundary_candidate"]
    empty=[c for c in candidates if c["candidate_status"]=="empty_boundary_candidate"]
    status="single_strong_candidate" if len(strong)==1 else "multiple_strong_candidates" if len(strong)>1 else "review_required" if review else "boundary_hint_empty" if empty else "no_usable_site_boundary_candidate"
    return {"phase":"phase2b2_site_discovery_only","database_writes":False,"migration_required":False,"candidate_count":len(candidates),"strong_candidate_count":len(strong),"review_candidate_count":len(review),"empty_boundary_hint_count":len(empty),"candidates":candidates,"recommendation":{"status":status,"logical_name":strong[0]["logical_name"] if len(strong)==1 else empty[0]["logical_name"] if (not strong and not review and empty) else None,"auto_create_site":False,"user_confirmation_required":True},"next_action":"User must confirm a valid organizer Site boundary before Site creation or persistent GIS import."}
