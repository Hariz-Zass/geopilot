from __future__ import annotations

import json
import uuid

import rasterio

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db import get_db_session
from app.core.errors import AppError
from app.models.user import User
from app.services.data_requirement_router import route_question
from app.services.isolation import SiteState
from app.schemas.planning_run import PlanningRunCreate
from app.services.planning_runs import create_planning_run
from app.services.planning_orchestrator import execute_planning_run
from app.schemas.track_b import (
    TrackBAnalysisRequest,
    TrackBAnalysisResponse,
    TrackBDatasetResponse,
    TrackBAIInterpretationResponse,
    TrackBComparisonRequest,
    TrackBComparisonResponse,
    TrackBPlannerDecisionRequest,
    TrackBPlannerDecisionResponse,
    TrackBAutoWorkflowRequest,
    TrackBWorkflowResponse,
    TrackBReadinessResponse,
)
from app.services.track_b_ai import (
    TrackBAIError,
    build_track_b_planner_decision,
    build_track_b_terrain_planner_decision,
    compare_track_b_urban_rural,
    interpret_track_b_analysis,
)
from app.services.track_b_workflow import run_track_b_hackathon_workflow
from app.services.track_b_smart_intake import inspect_organizer_package
from app.services.track_b_smart_import import prepare_import_plan
from app.services.track_b_smart_site_discovery import discover_site_candidates
from app.services.track_b_smart_site_resolution import SiteResolutionRequest, validate_site_resolution, parse_uploaded_boundary_geojson
from app.services.track_b_smart_spatial_import_plan import build_spatial_import_plan
from app.services.track_b_smart_import_all import ImportAllRequest, execute_persistent_import_all
from app.services.track_b_acceptance import assess_track_b_readiness
from app.services.track_b import (
    TrackBError,
    analyze_temporal_pair,
    archive_track_b_dataset,
    artifact_path,
    compose_track_b_report,
    ingest_raster_bundle,
    ingest_sentinel_archive,
    ingest_single_raster,
    list_track_b_datasets,
    render_dataset_quicklook,
)

router = APIRouter(prefix="/projects/{project_id}/track-b", tags=["Track B ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Geospatial & Satellite AI"])


def _error(exc: Exception, *, status: int = 422) -> AppError:
    return AppError(code="track_b_invalid", message=str(exc), status_code=status)


@router.get("/capabilities")
def capabilities(
    project_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        with rasterio.Env() as env:
            drivers = env.drivers()
        return {
            "track": "B",
            "evidence_architecture": "provenance_controlled",
            "evidence_policy": "provenance_controlled",
            "supported_inputs": {
                "geotiff": bool(drivers.get("GTiff")),
                "jp2": bool(drivers.get("JP2OpenJPEG")),
                "sentinel_zip_safe": bool(drivers.get("JP2OpenJPEG")),
                "multiband": True,
                "single_band_bundle": True,
            },
            "temporal_engines": ["auto", "ndvi", "ndwi", "ndbi", "spectral", "classified"],
            "alignment": "server_side_reprojection",
            "site_scope": "server_owned_geometry",
            "change_artifacts": ["GeoTIFF mask", "WGS84 GeoJSON regions", "evidence PDF"],
        }
    except Exception as exc:
        raise _error(exc, status=404) from exc


@router.get("/readiness", response_model=TrackBReadinessResponse)
def readiness(
    project_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        return assess_track_b_readiness(
            session, owner=current_user, project_id=project_id
        )
    except Exception as exc:
        raise _error(exc, status=404) from exc


@router.get("/datasets", response_model=list[TrackBDatasetResponse])
def datasets(
    project_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        return list_track_b_datasets(session, owner=current_user, project_id=project_id)
    except Exception as exc:
        raise _error(exc, status=404) from exc


@router.post("/datasets/{raster_id}/archive", response_model=TrackBDatasetResponse)
def archive_dataset(
    project_id: uuid.UUID,
    raster_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        return archive_track_b_dataset(
            session,
            owner=current_user,
            project_id=project_id,
            raster_id=raster_id,
        )
    except Exception as exc:
        session.rollback()
        raise _error(exc, status=404) from exc

@router.get("/datasets/{raster_id}/preview.png")
def preview_dataset(
    project_id: uuid.UUID,
    raster_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        dataset = next((d for d in list_track_b_datasets(session, owner=current_user, project_id=project_id) if d.id == raster_id), None)
        if dataset is None:
            raise TrackBError("Track B raster dataset not found.")
        payload = render_dataset_quicklook(dataset)
    except Exception as exc:
        raise _error(exc, status=404) from exc
    return Response(content=payload, media_type="image/png", headers={"Cache-Control": "private, max-age=60"})


@router.post("/datasets/upload", response_model=TrackBDatasetResponse, status_code=201)
async def upload_dataset(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    name: str = Form(...),
    site_id: uuid.UUID | None = Form(default=None),
    location_type: str = Form(...),
    temporal_role: str = Form(...),
    data_stage: str = Form(...),
    acquisition_datetime: str | None = Form(default=None),
    band_names: str | None = Form(default=None),
    scene_id: str | None = Form(default=None),
    auto_create_site: bool = Form(default=False),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if location_type not in {"urban", "rural"} or temporal_role not in {"before", "after", "reference"} or data_stage not in {"raw", "processed"}:
        raise _error(TrackBError("Invalid Track B location_type, temporal_role, or data_stage."))
    try:
        return await ingest_single_raster(
            session, owner=current_user, project_id=project_id, site_id=site_id, file=file, name=name,
            location_type=location_type, temporal_role=temporal_role, data_stage=data_stage,
            acquisition_datetime=acquisition_datetime, band_names_raw=band_names, scene_id=scene_id, auto_create_site=auto_create_site,
        )
    except Exception as exc:
        session.rollback()
        raise _error(exc) from exc


@router.post("/datasets/bundle", response_model=TrackBDatasetResponse, status_code=201)
async def upload_bundle(
    project_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    band_names: str = Form(...),
    name: str = Form(...),
    site_id: uuid.UUID | None = Form(default=None),
    location_type: str = Form(...),
    temporal_role: str = Form(...),
    data_stage: str = Form(default="raw"),
    acquisition_datetime: str | None = Form(default=None),
    scene_id: str | None = Form(default=None),
    auto_create_site: bool = Form(default=False),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if location_type not in {"urban", "rural"} or temporal_role not in {"before", "after", "reference"} or data_stage not in {"raw", "processed"}:
        raise _error(TrackBError("Invalid Track B location_type, temporal_role, or data_stage."))
    try:
        return await ingest_raster_bundle(
            session, owner=current_user, project_id=project_id, site_id=site_id, files=files, band_names_raw=band_names,
            name=name, location_type=location_type, temporal_role=temporal_role, data_stage=data_stage,
            acquisition_datetime=acquisition_datetime, scene_id=scene_id, auto_create_site=auto_create_site,
        )
    except Exception as exc:
        session.rollback()
        raise _error(exc) from exc


@router.post("/datasets/sentinel-archive", response_model=TrackBDatasetResponse, status_code=201)
async def upload_sentinel_archive(
    project_id: uuid.UUID,
    file: UploadFile = File(...),
    name: str = Form(...),
    site_id: uuid.UUID | None = Form(default=None),
    location_type: str = Form(...),
    temporal_role: str = Form(...),
    data_stage: str = Form(default="raw"),
    acquisition_datetime: str | None = Form(default=None),
    scene_id: str | None = Form(default=None),
    auto_create_site: bool = Form(default=False),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    if location_type not in {"urban", "rural"} or temporal_role not in {"before", "after", "reference"} or data_stage not in {"raw", "processed"}:
        raise _error(TrackBError("Invalid Track B location_type, temporal_role, or data_stage."))
    try:
        return await ingest_sentinel_archive(
            session, owner=current_user, project_id=project_id, site_id=site_id, file=file, name=name,
            location_type=location_type, temporal_role=temporal_role, data_stage=data_stage,
            acquisition_datetime=acquisition_datetime, scene_id=scene_id, auto_create_site=auto_create_site,
        )
    except Exception as exc:
        session.rollback()
        raise _error(exc) from exc


@router.post("/analyze", response_model=TrackBAnalysisResponse)
def analyze(
    project_id: uuid.UUID,
    payload: TrackBAnalysisRequest,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        return analyze_temporal_pair(session, owner=current_user, project_id=project_id, request=payload)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/analyses/{analysis_id}/ai-interpret", response_model=TrackBAIInterpretationResponse)
def ai_interpretation(
    project_id: uuid.UUID,
    analysis_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        # Enforce project ownership before reading the persisted analysis manifest.
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        return interpret_track_b_analysis(project_id=project_id, analysis_id=analysis_id)
    except TrackBAIError as exc:
        raise _error(exc, status=503) from exc
    except Exception as exc:
        raise _error(exc, status=404) from exc



# TRACKB_PLANNING_QUESTION_DISPATCHER_V1
def _planning_run_to_track_b_decision(*, analysis_id: uuid.UUID, question: str, run):
    provider_metadata = run.provider_metadata or {}
    evidence = run.evidence or []
    limitations = list(run.limitations or [])
    refs = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") or {}
        ref = payload.get("citation_label") or payload.get("document_title") or item.get("tool_name")
        if ref:
            refs.append(str(ref))
    refs = list(dict.fromkeys(refs))
    completed = run.status == "completed" and bool(run.synthesis)
    synthesis = (run.synthesis or "").strip()
    if not synthesis:
        synthesis = "GeoPilot could not produce a grounded planning answer from the currently available validated evidence."

    evidence_summary_lines = []
    seen_summary_lines = set()
    for item in evidence:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") or {}
        tool_name = str(item.get("tool_name") or "validated_evidence")

        if tool_name == "documents.search":
            title = str(payload.get("document_title") or "").strip()
            citation = str(payload.get("citation_label") or "").strip()
            authority = str(payload.get("authority") or "").strip()
            page_number = payload.get("page_number")

            label = title or citation or "Planning document evidence"
            details = []
            if authority and authority.casefold() not in label.casefold():
                details.append(authority)
            if citation and citation != label:
                details.append(citation)
            elif page_number is not None and f"p. {page_number}" not in label:
                details.append(f"p. {page_number}")

            line = f"- **{label}**"
            if details:
                line += " â€” " + " Â· ".join(details)
        else:
            line = f"- **{tool_name}** â€” validated project evidence"

        if line not in seen_summary_lines:
            seen_summary_lines.add(line)
            evidence_summary_lines.append(line)

    if evidence_summary_lines:
        evidence_summary = "### Validated evidence used\n" + "\n".join(evidence_summary_lines)
    elif refs:
        evidence_summary = "### Validated evidence references\n" + "\n".join(f"- {ref}" for ref in refs)
    else:
        evidence_summary = "No validated evidence reference was available for this response."

    return {
        "analysis_id": analysis_id,
        "provider": str(provider_metadata.get("provider") or "planning_orchestrator"),
        "model": str(provider_metadata.get("model") or "evidence-router"),
        "confidence": "moderate" if completed else "limited",
        "priority": "monitor" if completed else "evidence_limited",
        "decision_title": "Grounded planning evidence response",
        "issue": question,
        "planning_implication": synthesis,
        "evidence_summary": evidence_summary,
        "recommended_actions": [],
        "evidence_refs": refs,
        "limitations": limitations,
        "planner_question": question,
        "evidence_architecture": "provenance_controlled",
        "evidence_policy": "provenance_controlled",
        "professional_review_required": True,
    }

def _run_track_b_planning_question(session: Session, *, owner: User, project_id: uuid.UUID, site_id: uuid.UUID, analysis_id: uuid.UUID, question: str):
    run = create_planning_run(session, owner=owner, project_id=project_id, site_id=site_id, request=PlanningRunCreate(question=question, development_intent=None), site_state=SiteState.AVAILABLE)
    run = execute_planning_run(session, owner=owner, project_id=project_id, site_id=site_id, run_id=run.id, site_state=SiteState.AVAILABLE)
    return _planning_run_to_track_b_decision(analysis_id=analysis_id, question=question, run=run)

@router.post("/analyses/{analysis_id}/decision-workspace", response_model=TrackBPlannerDecisionResponse)
def planner_decision_workspace(
    project_id: uuid.UUID,
    analysis_id: uuid.UUID,
    payload: TrackBPlannerDecisionRequest,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        question = (payload.planner_question or "").strip()
        route = route_question(question) if question else None
        if route is not None and route.capability == "terrain_measurement":
            return build_track_b_terrain_planner_decision(
                session=session,
                owner=current_user,
                project_id=project_id,
                analysis_id=analysis_id,
                planner_question=question,
            )
        if route is not None and (
            route.capability == "planning_multi_evidence"
            or "documents.search" in route.tools
        ):
            manifest_path = artifact_path(
                project_id,
                analysis_id,
                "analysis.json",
            )
            if not manifest_path.is_file():
                raise TrackBAIError(
                    "Track B analysis manifest is not available for planning-document research."
                )
            analysis = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
            site_id = analysis.get("site_id")
            if not site_id:
                raise TrackBAIError("Planning-document research requires the Track B analysis to be linked to a Site.")
            return _run_track_b_planning_question(
                session,
                owner=current_user,
                project_id=project_id,
                site_id=uuid.UUID(str(site_id)),
                analysis_id=analysis_id,
                question=question,
            )
        return build_track_b_planner_decision(
            project_id=project_id,
            analysis_id=analysis_id,
            planner_question=payload.planner_question,
        )
    except TrackBAIError as exc:
        raise _error(exc, status=503) from exc
    except Exception as exc:
        raise _error(exc, status=404) from exc


@router.post("/ai/urban-rural-compare", response_model=TrackBComparisonResponse)
def urban_rural_compare(
    project_id: uuid.UUID,
    payload: TrackBComparisonRequest,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        return compare_track_b_urban_rural(
            project_id=project_id,
            urban_analysis_id=payload.urban_analysis_id,
            rural_analysis_id=payload.rural_analysis_id,
        )
    except TrackBAIError as exc:
        raise _error(exc, status=503) from exc
    except Exception as exc:
        raise _error(exc, status=404) from exc


# SMART_ORGANIZER_INTAKE_V1
# SMART_ORGANIZER_PHASE2A
# SMART_ORGANIZER_PHASE2B2_SITE_DISCOVERY
# SMART_ORGANIZER_PHASE2B3_SITE_RESOLUTION
# SMART_ORGANIZER_PHASE2C2_SPATIAL_IMPORT_PLAN
# SMART_ORGANIZER_PHASE2C3B_PERSISTENT_IMPORT_ALL
@router.post("/organizer-intake/import-all")
async def organizer_intake_import_all(
    project_id: uuid.UUID,
    site_name: str = Form(...),
    site_geometry_json: str = Form(...),
    site_source_ref: str | None = Form(default=None),
    user_confirmed: bool = Form(False),
    role_assignments_json: str = Form("{}"),
    allow_invalid_geometry_skip: bool = Form(False),
    execute_persistent: bool = Form(False),
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        try:
            site_geometry = json.loads(site_geometry_json)
            role_assignments = json.loads(role_assignments_json)
        except Exception as exc:
            raise TrackBError(
                "site_geometry_json and role_assignments_json must be valid JSON."
            ) from exc
        if not isinstance(role_assignments, dict):
            raise TrackBError("role_assignments_json must be a JSON object.")

        payload = ImportAllRequest(
            site_name=site_name,
            site_geometry=site_geometry,
            site_source_ref=site_source_ref,
            user_confirmed=user_confirmed,
            role_assignments=role_assignments,
            allow_invalid_geometry_skip=allow_invalid_geometry_skip,
            execute_persistent=execute_persistent,
        )
        return await execute_persistent_import_all(
            session,
            owner=current_user,
            project_id=project_id,
            files=files,
            request=payload,
        )
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        session.rollback()
        raise _error(exc, status=500) from exc

@router.post("/organizer-intake/import-plan")
async def organizer_intake_import_plan(
    project_id: uuid.UUID,
    site_name: str = Form(...),
    site_geometry_json: str = Form(...),
    site_source_ref: str | None = Form(default=None),
    user_confirmed: bool = Form(False),
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        try:
            site_geometry = json.loads(site_geometry_json)
        except Exception as exc:
            raise TrackBError("site_geometry_json must be valid GeoJSON geometry JSON.") from exc

        validated = validate_site_resolution(
            SiteResolutionRequest(
                site_name=site_name,
                mode="manual_draw",
                geometry=site_geometry,
                source_ref=site_source_ref,
                user_confirmed=user_confirmed,
            )
        )
        if not validated.get("ready_for_site_creation"):
            raise TrackBError("Confirmed valid Site boundary is required before import planning.")

        return await build_spatial_import_plan(
            files=files,
            site_geometry=validated["geometry"],
            site_name=validated["site_name"],
            site_source_ref=site_source_ref,
            user_confirmed=True,
        )
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc

@router.post("/organizer-intake/site-resolution/validate")
async def organizer_intake_site_resolution_validate(
    project_id: uuid.UUID,
    payload: SiteResolutionRequest,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        return validate_site_resolution(payload)
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc


@router.post("/organizer-intake/site-resolution/upload")
async def organizer_intake_site_resolution_upload(
    project_id: uuid.UUID,
    site_name: str = Form(...),
    user_confirmed: bool = Form(False),
    file: UploadFile = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        data = await file.read()
        return parse_uploaded_boundary_geojson(
            site_name=site_name,
            payload=data,
            source_ref=file.filename or "uploaded_boundary",
            user_confirmed=user_confirmed,
        )
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc

@router.post("/organizer-intake/site-candidates")
async def organizer_intake_site_candidates(
    project_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        return await discover_site_candidates(files)
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc

@router.post("/organizer-intake/prepare")
async def organizer_intake_prepare(
    project_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        return await prepare_import_plan(files)
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc

@router.post("/organizer-intake/inspect")
async def organizer_intake_inspect(
    project_id: uuid.UUID,
    files: list[UploadFile] = File(...),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        return await inspect_organizer_package(files)
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc


@router.post("/workflow/hackathon-run", response_model=TrackBWorkflowResponse)
def hackathon_run(
    project_id: uuid.UUID,
    payload: TrackBAutoWorkflowRequest,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        return run_track_b_hackathon_workflow(
            session, owner=current_user, project_id=project_id, request=payload
        )
    except TrackBError as exc:
        raise _error(exc, status=422) from exc
    except Exception as exc:
        raise _error(exc, status=500) from exc


@router.get("/analyses/{analysis_id}/report")
def analysis_report(
    project_id: uuid.UUID,
    analysis_id: uuid.UUID,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        path = compose_track_b_report(project_id, analysis_id)
    except Exception as exc:
        raise _error(exc, status=404) from exc
    return FileResponse(path, media_type="application/pdf", filename="GeoPilot_TrackB_Evidence_Report.pdf")


@router.get("/artifacts/{analysis_id}/{filename}")
def artifact(
    project_id: uuid.UUID,
    analysis_id: uuid.UUID,
    filename: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
):
    # Project ownership is enforced by listing datasets within project scope before serving artifacts.
    try:
        list_track_b_datasets(session, owner=current_user, project_id=project_id)
        path = artifact_path(project_id, analysis_id, filename)
    except Exception as exc:
        raise _error(exc, status=404) from exc
    media = "application/geo+json" if filename.endswith(".geojson") else "image/tiff"
    return FileResponse(path, media_type=media, filename=filename)











