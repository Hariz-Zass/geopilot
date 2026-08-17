from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any

import rasterio
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.raster import RasterDataset
from app.models.user import User
from app.services.track_b import TrackBError, _local_path, list_track_b_datasets
from app.services.track_b_workflow import _select_pair


def _recommended_mode(before: RasterDataset, after: RasterDataset) -> str:
    common = set(before.band_names) & set(after.band_names)
    if {"B04", "B08"} <= common:
        return "ndvi"
    if {"B03", "B08"} <= common:
        return "ndwi"
    if {"B08", "B11"} <= common:
        return "ndbi"
    if (
        (before.provenance or {}).get("data_stage") == "processed"
        and (after.provenance or {}).get("data_stage") == "processed"
        and before.band_count == after.band_count == 1
    ):
        return "classified"
    return "spectral"


def _verify_local_assets(dataset: RasterDataset) -> tuple[bool, str]:
    provenance = dataset.provenance or {}
    if provenance.get("synthetic_fixture") is True:
        return False, "Synthetic QA fixture is not eligible as competition evidence."
    assets = provenance.get("assets")
    if isinstance(assets, dict) and assets:
        for band, asset in assets.items():
            if not isinstance(asset, dict):
                return False, f"Band {band} has invalid asset provenance."
            uri = asset.get("uri")
            checksum = asset.get("checksum_sha256")
            try:
                path = _local_path(uri)
            except TrackBError as exc:
                return False, str(exc)
            if checksum and hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                return False, f"Band {band} checksum does not match immutable provenance."
        return True, f"{len(assets)} local band assets verified."
    try:
        path = _local_path(dataset.source_uri)
    except TrackBError as exc:
        return False, str(exc)
    if hashlib.sha256(path.read_bytes()).hexdigest() != dataset.checksum_sha256:
        return False, "Raster checksum does not match immutable provenance."
    return True, "Local raster artifact and checksum verified."


def _pair_payload(datasets: list[RasterDataset], location_type: str) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    try:
        before, after = _select_pair(datasets, location_type)
    except TrackBError as exc:
        return {
            "location_type": location_type,
            "ready": False,
            "before_raster_id": None,
            "after_raster_id": None,
            "site_id": None,
            "data_stage": None,
            "recommended_mode": None,
            "detail": str(exc),
        }, warnings

    if (before.provenance or {}).get("synthetic_fixture") or (after.provenance or {}).get("synthetic_fixture"):
        return {
            "location_type": location_type,
            "ready": False,
            "before_raster_id": before.id,
            "after_raster_id": after.id,
            "site_id": before.site_id,
            "data_stage": (before.provenance or {}).get("data_stage"),
            "recommended_mode": _recommended_mode(before, after),
            "detail": "Selected pair is a synthetic QA fixture and is blocked from competition readiness.",
        }, warnings

    if before.acquisition_datetime and after.acquisition_datetime and before.acquisition_datetime >= after.acquisition_datetime:
        return {
            "location_type": location_type,
            "ready": False,
            "before_raster_id": before.id,
            "after_raster_id": after.id,
            "site_id": before.site_id,
            "data_stage": (before.provenance or {}).get("data_stage"),
            "recommended_mode": _recommended_mode(before, after),
            "detail": "Before timestamp is not earlier than after timestamp.",
        }, warnings

    for dataset in (before, after):
        ok, detail = _verify_local_assets(dataset)
        if not ok:
            return {
                "location_type": location_type,
                "ready": False,
                "before_raster_id": before.id,
                "after_raster_id": after.id,
                "site_id": before.site_id,
                "data_stage": (before.provenance or {}).get("data_stage"),
                "recommended_mode": _recommended_mode(before, after),
                "detail": f"{dataset.name}: {detail}",
            }, warnings

    if not before.acquisition_datetime or not after.acquisition_datetime:
        warnings.append(f"{location_type.title()} pair has incomplete acquisition datetime metadata.")

    return {
        "location_type": location_type,
        "ready": True,
        "before_raster_id": before.id,
        "after_raster_id": after.id,
        "site_id": before.site_id,
        "data_stage": (before.provenance or {}).get("data_stage"),
        "recommended_mode": _recommended_mode(before, after),
        "detail": "Before/after pair is locally available, lineage-verified, and analysis-compatible.",
    }, warnings


def assess_track_b_readiness(
    session: Session, *, owner: User, project_id: uuid.UUID
) -> dict[str, Any]:
    settings = get_settings()
    datasets = list_track_b_datasets(session, owner=owner, project_id=project_id)
    organizer = [
        d for d in datasets
        if d.source_kind == "upload"
        and (d.provenance or {}).get("synthetic_fixture") is not True
        and not d.is_archived
        and d.status == "ready"
    ]

    checks: list[dict[str, str]] = []
    blockers: list[str] = []
    warnings: list[str] = []


    with rasterio.Env() as env:
        drivers = env.drivers()
    raster_ok = bool(drivers.get("GTiff")) and bool(drivers.get("JP2OpenJPEG"))
    checks.append({
        "key": "raster_runtime",
        "label": "GeoTIFF + Sentinel JP2 runtime",
        "status": "pass" if raster_ok else "block",
        "detail": "GTiff and JP2OpenJPEG drivers are available." if raster_ok else "Required raster driver support is incomplete.",
    })
    if not raster_ok:
        blockers.append("Restore GTiff and JP2OpenJPEG runtime support.")

    urban, urban_warnings = _pair_payload(organizer, "urban")
    rural, rural_warnings = _pair_payload(organizer, "rural")
    warnings.extend(urban_warnings + rural_warnings)
    for pair in (urban, rural):
        checks.append({
            "key": f"{pair['location_type']}_temporal_pair",
            "label": f"{pair['location_type'].title()} T1/T2 evidence pair",
            "status": "pass" if pair["ready"] else "block",
            "detail": pair["detail"],
        })
        if not pair["ready"]:
            blockers.append(pair["detail"])

    ai_configured = bool(settings.openai_api_key) or bool(settings.ollama_base_url and settings.ollama_planning_model)
    checks.append({
        "key": "ai_planning_provider",
        "label": "Grounded AI planning provider configuration",
        "status": "pass" if ai_configured else "block",
        "detail": "At least one planning AI provider is configured; runtime connectivity is verified when the mission executes." if ai_configured else "No planning AI provider is configured.",
    })
    if not ai_configured:
        blockers.append("Configure OpenAI or Ollama planning AI before judge-facing mission execution.")

    checks.append({
        "key": "professional_boundary",
        "label": "Professional review boundary",
        "status": "pass",
        "detail": "GeoPilot outputs decision support, evidence lineage, limitations, and professional-review requirements rather than statutory approval claims.",
    })

    if blockers:
        status = "blocked" if len(blockers) >= 2 or not urban["ready"] or not rural["ready"] else "partial"
        next_action = "Resolve the listed blockers, then rerun Track B readiness before starting the full mission."
    else:
        status = "ready"
        next_action = "Run the full Track B mission and verify AI outputs against their cited evidence before presentation."

    return {
        "status": status,
        "evidence_architecture": "provenance_controlled",
        "evidence_policy": "provenance_controlled",
        "dataset_count": len(datasets),
        "eligible_dataset_count": len(organizer),
        "urban": urban,
        "rural": rural,
        "checks": checks,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "next_action": next_action,
        "professional_review_required": True,
    }

