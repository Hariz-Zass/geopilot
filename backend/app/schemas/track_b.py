from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


LocationType = Literal["urban", "rural"]
TemporalRole = Literal["before", "after", "reference"]
DataStage = Literal["raw", "processed"]
AnalysisMode = Literal["auto", "ndvi", "ndwi", "ndbi", "spectral", "classified"]


class TrackBDatasetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID | None
    name: str
    source_kind: str
    provider: str | None
    collection: str | None
    scene_id: str | None
    acquisition_datetime: str | None
    crs: str
    width: int
    height: int
    band_count: int
    band_names: list[str]
    pixel_size: dict
    bounds: dict
    nodata: dict
    source_uri: str | None
    checksum_sha256: str
    provenance: dict
    status: str
    is_archived: bool
    created_at: datetime


class TrackBAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    site_id: uuid.UUID
    before_raster_id: uuid.UUID
    after_raster_id: uuid.UUID
    mode: AnalysisMode = "auto"
    absolute_delta_threshold: float = Field(default=0.2, gt=0, le=10)
    minimum_usable_coverage_percent: float = Field(default=90.0, ge=1, le=100)

    @model_validator(mode="after")
    def distinct_scenes(self):
        if self.before_raster_id == self.after_raster_id:
            raise ValueError("before and after raster IDs must be distinct")
        return self


class TrackBMetric(BaseModel):
    key: str
    label: str
    value: float | int | str
    unit: str | None = None


class TrackBAnalysisResponse(BaseModel):
    analysis_id: uuid.UUID
    project_id: uuid.UUID
    site_id: uuid.UUID
    mode: str
    method: str
    before_raster_id: uuid.UUID
    after_raster_id: uuid.UUID
    before_datetime: str | None
    after_datetime: str | None
    usable_coverage_percent: float
    changed_pixel_count: int
    valid_pixel_count: int
    changed_percentage: float
    changed_area_hectares: float | None
    mean_before: float | None = None
    mean_after: float | None = None
    metrics: list[TrackBMetric] = Field(default_factory=list)
    change_geojson_url: str | None = None
    change_mask_url: str | None = None
    report_url: str | None = None
    evidence: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    summary: str


class TrackBAIInsight(BaseModel):
    title: str
    finding: str
    planning_relevance: str
    recommended_action: str
    evidence_refs: list[str] = Field(default_factory=list)


class TrackBAIInterpretationResponse(BaseModel):
    analysis_id: uuid.UUID
    provider: str
    model: str
    confidence: Literal["high", "moderate", "limited"]
    executive_summary: str
    planner_problem: str
    insights: list[TrackBAIInsight] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    evidence_architecture: str = "provenance_controlled"
    evidence_policy: str = "provenance_controlled"
    professional_review_required: bool = True


class TrackBComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    urban_analysis_id: uuid.UUID
    rural_analysis_id: uuid.UUID

    @model_validator(mode="after")
    def distinct_analyses(self):
        if self.urban_analysis_id == self.rural_analysis_id:
            raise ValueError("urban and rural analysis IDs must be distinct")
        return self


class TrackBComparisonResponse(BaseModel):
    provider: str
    model: str
    confidence: Literal["high", "moderate", "limited"]
    strategic_summary: str
    urban_priority: str
    rural_priority: str
    shared_planning_problem: str
    comparative_insights: list[TrackBAIInsight] = Field(default_factory=list)
    priority_actions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    evidence_architecture: str = "provenance_controlled"
    evidence_policy: str = "provenance_controlled"
    professional_review_required: bool = True

class TrackBPlannerDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    planner_question: str | None = Field(default=None, max_length=1000)


class TrackBPlannerDecisionAction(BaseModel):
    action: str
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)
    verification_needed: str


class TrackBPlannerDecisionResponse(BaseModel):
    analysis_id: uuid.UUID
    provider: str
    model: str
    confidence: Literal["high", "moderate", "limited"]
    priority: Literal["high", "elevated", "monitor", "evidence_limited"]
    decision_title: str
    issue: str
    planning_implication: str
    evidence_summary: str
    recommended_actions: list[TrackBPlannerDecisionAction] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    planner_question: str | None = None
    evidence_architecture: str = "provenance_controlled"
    evidence_policy: str = "provenance_controlled"
    professional_review_required: bool = True

class TrackBAutoWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: AnalysisMode = "auto"
    absolute_delta_threshold: float = Field(default=0.2, gt=0, le=10)
    minimum_usable_coverage_percent: float = Field(default=90.0, ge=1, le=100)
    planner_question: str | None = Field(default=None, max_length=1000)


class TrackBWorkflowStage(BaseModel):
    key: str
    label: str
    status: Literal["pass", "failed", "skipped"]
    detail: str


class TrackBWorkflowResponse(BaseModel):
    workflow_id: uuid.UUID
    status: Literal["complete", "partial"]
    urban_analysis: TrackBAnalysisResponse
    rural_analysis: TrackBAnalysisResponse
    urban_ai: TrackBAIInterpretationResponse | None = None
    rural_ai: TrackBAIInterpretationResponse | None = None
    urban_decision: TrackBPlannerDecisionResponse | None = None
    rural_decision: TrackBPlannerDecisionResponse | None = None
    comparison: TrackBComparisonResponse | None = None
    stages: list[TrackBWorkflowStage] = Field(default_factory=list)
    evidence_architecture: str = "provenance_controlled"
    evidence_policy: str = "provenance_controlled"
    professional_review_required: bool = True



class TrackBReadinessCheck(BaseModel):
    key: str
    label: str
    status: Literal["pass", "warn", "block"]
    detail: str


class TrackBReadinessPair(BaseModel):
    location_type: LocationType
    ready: bool
    before_raster_id: uuid.UUID | None = None
    after_raster_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    data_stage: DataStage | None = None
    recommended_mode: AnalysisMode | None = None
    detail: str


class TrackBReadinessResponse(BaseModel):
    status: Literal["ready", "partial", "blocked"]
    evidence_architecture: str = "provenance_controlled"
    evidence_policy: str = "provenance_controlled"
    dataset_count: int
    eligible_dataset_count: int
    urban: TrackBReadinessPair
    rural: TrackBReadinessPair
    checks: list[TrackBReadinessCheck] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_action: str
    professional_review_required: bool = True

