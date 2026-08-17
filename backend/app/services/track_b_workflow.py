from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.raster import RasterDataset
from app.models.user import User
from app.schemas.track_b import TrackBAutoWorkflowRequest, TrackBAnalysisRequest
from app.services.track_b import TrackBError, analyze_temporal_pair, list_track_b_datasets
from app.services.track_b_ai import (
    TrackBAIError,
    build_track_b_planner_decision,
    compare_track_b_urban_rural,
    interpret_track_b_analysis,
)


def _workflow_root(project_id: uuid.UUID, workflow_id: uuid.UUID) -> Path:
    root = Path(get_settings().raster_storage_root).expanduser().resolve()
    path = (root / "analysis" / str(project_id) / "workflows" / str(workflow_id)).resolve()
    if root != path and root not in path.parents:
        raise TrackBError("Track B workflow path escaped configured raster storage root.")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _select_pair(datasets: list[RasterDataset], location_type: str) -> tuple[RasterDataset, RasterDataset]:
    candidates = [
        d for d in datasets
        if not getattr(d, "is_archived", False)
        and bool(d.site_id)
        and bool(d.checksum_sha256)
        and bool(d.source_uri)
        and (d.provenance or {}).get("synthetic_fixture") is not True
        and (d.provenance or {}).get("location_type") == location_type
        and (d.provenance or {}).get("temporal_role") in {"before", "after"}
        and d.site_id is not None
    ]
    groups: dict[tuple[str, str], list[RasterDataset]] = {}
    for d in candidates:
        key = (str(d.site_id), str((d.provenance or {}).get("data_stage") or ""))
        groups.setdefault(key, []).append(d)
    viable: list[tuple[Any, RasterDataset, RasterDataset]] = []
    for items in groups.values():
        before = [d for d in items if (d.provenance or {}).get("temporal_role") == "before"]
        after = [d for d in items if (d.provenance or {}).get("temporal_role") == "after"]
        if not before or not after:
            continue
        before.sort(key=lambda d: (d.acquisition_datetime or "", d.created_at), reverse=True)
        after.sort(key=lambda d: (d.acquisition_datetime or "", d.created_at), reverse=True)
        viable.append((max(before[0].created_at, after[0].created_at), before[0], after[0]))
    if not viable:
        raise TrackBError(
            f"Workflow requires an eligible {location_type} before/after pair "
            "with the same Site and data stage."
        )
    viable.sort(key=lambda x: x[0], reverse=True)
    return viable[0][1], viable[0][2]


def run_track_b_hackathon_workflow(
    session: Session, *, owner: User, project_id: uuid.UUID, request: TrackBAutoWorkflowRequest
) -> dict[str, Any]:
    datasets = list_track_b_datasets(session, owner=owner, project_id=project_id)
    urban_before, urban_after = _select_pair(datasets, "urban")
    rural_before, rural_after = _select_pair(datasets, "rural")
    workflow_id = uuid.uuid4()
    stages: list[dict[str, str]] = []

    def analysis_request(before: RasterDataset, after: RasterDataset) -> TrackBAnalysisRequest:
        if before.site_id is None or before.site_id != after.site_id:
            raise TrackBError("Selected Track B temporal pair does not share one server-owned Site.")
        return TrackBAnalysisRequest(
            site_id=before.site_id, before_raster_id=before.id, after_raster_id=after.id,
            mode=request.mode, absolute_delta_threshold=request.absolute_delta_threshold,
            minimum_usable_coverage_percent=request.minimum_usable_coverage_percent,
        )

    urban = analyze_temporal_pair(session, owner=owner, project_id=project_id, request=analysis_request(urban_before, urban_after))
    stages.append({"key":"urban_analysis","label":"Urban temporal intelligence","status":"pass","detail":urban["summary"]})
    rural = analyze_temporal_pair(session, owner=owner, project_id=project_id, request=analysis_request(rural_before, rural_after))
    stages.append({"key":"rural_analysis","label":"Rural temporal intelligence","status":"pass","detail":rural["summary"]})

    ai_outputs: dict[str, Any] = {"urban_ai": None, "rural_ai": None, "urban_decision": None, "rural_decision": None, "comparison": None}
    ai_steps = [
        ("urban_ai", "Urban AI planning interpretation", lambda: interpret_track_b_analysis(project_id=project_id, analysis_id=urban["analysis_id"])),
        ("rural_ai", "Rural AI planning interpretation", lambda: interpret_track_b_analysis(project_id=project_id, analysis_id=rural["analysis_id"])),
        ("urban_decision", "Urban planner decision brief", lambda: build_track_b_planner_decision(project_id=project_id, analysis_id=urban["analysis_id"], planner_question=request.planner_question)),
        ("rural_decision", "Rural planner decision brief", lambda: build_track_b_planner_decision(project_id=project_id, analysis_id=rural["analysis_id"], planner_question=request.planner_question)),
        ("comparison", "Urban vs rural planning intelligence", lambda: compare_track_b_urban_rural(project_id=project_id, urban_analysis_id=urban["analysis_id"], rural_analysis_id=rural["analysis_id"])),
    ]
    for key, label, fn in ai_steps:
        try:
            ai_outputs[key] = fn()
            stages.append({"key":key,"label":label,"status":"pass","detail":"Grounded AI output generated from provenance-controlled evidence."})
        except TrackBAIError as exc:
            stages.append({"key":key,"label":label,"status":"failed","detail":str(exc)})

    status = "complete" if all(s["status"] == "pass" for s in stages) else "partial"
    response = {
        "workflow_id": workflow_id, "status": status, "urban_analysis": urban, "rural_analysis": rural,
        **ai_outputs, "stages": stages, "evidence_policy":"provenance_controlled", "professional_review_required": True,
    }
    folder = _workflow_root(project_id, workflow_id)
    (folder / "workflow.json").write_text(json.dumps(response, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return response

