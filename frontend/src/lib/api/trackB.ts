import { frontendEnv } from "../../config/env";
import { apiClient } from "./client";

export type TrackBOrganizerIntakeItem = {
  index:number; filename:string; extension:string; content_type:string|null; size_bytes:number;
  classification:string; confidence:"high"|"moderate"|"low"; location_type:"urban"|"rural"|null;
  temporal_role:"before"|"after"|"reference"|null; data_stage:"raw"|"processed"|null; band_name:string|null;
  acquisition_datetime:string|null; suggested_applicability_role:"zoning"|"land_use"|"planning_block"|"planning_subzone"|null;
  requires_confirmation:boolean; metadata:Record<string,unknown>; issues:string[];
};
export type TrackBOrganizerIntakeReport = {
  phase:"inspect_only"; database_writes:false; file_count:number; supported_or_reviewable_count:number;
  requires_confirmation_count:number; blocker_count:number; class_counts:Record<string,number>;
  blockers:string[]; items:TrackBOrganizerIntakeItem[]; next_action:string;
};

// SMART_ORGANIZER_PHASE2D1_FRONTEND_TYPES
export type TrackBOrganizerSiteCandidate = {
  logical_name:string; format:string|null; source_checksum_sha256:string|null;
  normalized_crs:string|null; feature_count:number; geometry_types:string[];
  candidate_status:string; requires_confirmation:boolean; reasons:string[];
  bounds:number[]|null; union_geometry:Record<string,unknown>|null;
};

export type TrackBOrganizerSiteDiscovery = {
  phase:string; database_writes:false; migration_required:false;
  candidate_count:number; strong_candidate_count:number; review_candidate_count:number;
  empty_boundary_hint_count:number; candidates:TrackBOrganizerSiteCandidate[];
  recommendation:{status:string;logical_name:string|null;auto_create_site:false;user_confirmation_required:true};
  next_action:string;
};

export type TrackBOrganizerSiteResolution = {
  phase:string; status:string; database_writes:false; migration_required:false;
  site_name:string; mode:string; source_ref:string|null; geometry_valid:boolean;
  geometry_type?:string; bounds?:number[]; geometry?:Record<string,unknown>;
  ready_for_site_creation:boolean; limitations:string[]; next_action?:string;
};

export type TrackBOrganizerImportPlanDataset = {
  logical_name:string; format:string|null; source_feature_count:number;
  valid_geometry_feature_count:number; invalid_geometry_feature_count:number;
  intersecting_feature_count:number; intersection_ratio_percent:number;
  geometry_types:string[]; intersecting_geometry_types:string[];
  decision:"IMPORT_CANDIDATE"|"SKIP_NO_OVERLAP"|"SKIP_EMPTY"|"REVIEW_INVALID_GEOMETRY";
  decision_reason:string; applicability_role:string|null; role_confirmation_required:boolean;
  persistent_write_authorized:false;
};

export type TrackBOrganizerImportPlan = {
  phase:string; database_writes:false; migration_required:false;
  site:{name:string;source_ref:string|null;user_confirmed:true;geometry_type:string;bounds:number[];crs:string};
  dataset_count:number; datasets:TrackBOrganizerImportPlanDataset[];
  totals:{
    source_features:number; valid_geometry_features:number; intersecting_features:number;
    import_candidate_datasets:number; skip_empty_datasets:number;
    skip_no_overlap_datasets:number; review_datasets:number;
  };
  blocking_conditions:string[]; ready_for_phase2c3:boolean; next_action:string;
};

export type TrackBOrganizerImportAllResponse = {
  phase:string; status:string; database_writes:boolean; committed:boolean;
  site_id?:string; site_created:boolean; site_duplicate_reused?:boolean;
  layers_created:number; layers_reused?:number; features_created:number;
  features_duplicates_skipped?:number;
  import_plan?:Array<{logical_name:string;role:string;intersecting_feature_count:number;invalid_geometry_count:number;geometry_type:string;source_checksum_sha256:string|null}>;
  imported_layers?:Array<{logical_name:string;layer_id:string;role:string;layer_created:boolean;feature_created_count:number;feature_duplicate_count:number}>;
  skipped:Array<Record<string,unknown>>; reviews:Array<Record<string,unknown>>;
  message?:string;
};

export type TrackBDataset = {
  id: string;
  project_id: string;
  site_id: string | null;
  name: string;
  source_kind: string;
  provider: string | null;
  collection: string | null;
  scene_id: string | null;
  acquisition_datetime: string | null;
  crs: string;
  width: number;
  height: number;
  band_count: number;
  band_names: string[];
  pixel_size: Record<string, number>;
  bounds: Record<string, number>;
  nodata: Record<string, unknown>;
  source_uri: string | null;
  checksum_sha256: string;
  provenance: Record<string, unknown>;
  status: string;
  is_archived: boolean;
  created_at: string;
};

export type TrackBAnalysis = {
  analysis_id: string;
  project_id: string;
  site_id: string;
  mode: string;
  method: string;
  before_raster_id: string;
  after_raster_id: string;
  before_datetime: string | null;
  after_datetime: string | null;
  usable_coverage_percent: number;
  changed_pixel_count: number;
  valid_pixel_count: number;
  changed_percentage: number;
  changed_area_hectares: number | null;
  mean_before: number | null;
  mean_after: number | null;
  metrics: Array<{ key: string; label: string; value: string | number; unit: string | null }>;
  change_geojson_url: string | null;
  change_mask_url: string | null;
  report_url: string | null;
  evidence: Array<Record<string, unknown>>;
  limitations: string[];
  summary: string;
};

export type TrackBAIInterpretation = {
  analysis_id: string;
  provider: string;
  model: string;
  confidence: "high" | "moderate" | "limited";
  executive_summary: string;
  planner_problem: string;
  insights: Array<{ title: string; finding: string; planning_relevance: string; recommended_action: string; evidence_refs: string[] }>;
  next_actions: string[];
  caveats: string[];
  evidence_policy: string;
  professional_review_required: boolean;
};

export type TrackBPlannerDecision = {
  analysis_id: string;
  provider: string;
  model: string;
  confidence: "high" | "moderate" | "limited";
  priority: "high" | "elevated" | "monitor" | "evidence_limited";
  decision_title: string;
  issue: string;
  planning_implication: string;
  evidence_summary: string;
  recommended_actions: Array<{ action: string; rationale: string; evidence_refs: string[]; verification_needed: string }>;
  evidence_refs: string[];
  limitations: string[];
  planner_question: string | null;
  evidence_policy: string;
  professional_review_required: boolean;
};


export type TrackBWorkflowStage = { key: string; label: string; status: "pass" | "failed" | "skipped"; detail: string };
export type TrackBWorkflow = {
  workflow_id: string; status: "complete" | "partial"; urban_analysis: TrackBAnalysis; rural_analysis: TrackBAnalysis;
  urban_ai: TrackBAIInterpretation | null; rural_ai: TrackBAIInterpretation | null;
  urban_decision: TrackBPlannerDecision | null; rural_decision: TrackBPlannerDecision | null;
  comparison: { provider: string; model: string; confidence: "high" | "moderate" | "limited"; strategic_summary: string; urban_priority: string; rural_priority: string; shared_planning_problem: string; comparative_insights: Array<{title:string; finding:string; planning_relevance:string; recommended_action:string; evidence_refs:string[]}>; priority_actions:string[]; caveats:string[]; evidence_policy:string; professional_review_required:boolean } | null;
  stages: TrackBWorkflowStage[]; evidence_policy: string; professional_review_required: boolean;
};


export type TrackBReadinessPair = {
  location_type: "urban" | "rural"; ready: boolean; before_raster_id: string | null; after_raster_id: string | null;
  site_id: string | null; data_stage: "raw" | "processed" | null; recommended_mode: "auto" | "ndvi" | "ndwi" | "ndbi" | "spectral" | "classified" | null; detail: string;
};
export type TrackBReadiness = {
  status: "ready" | "partial" | "blocked"; competition_mode: boolean; evidence_policy: string; dataset_count: number; organizer_dataset_count: number;
  urban: TrackBReadinessPair; rural: TrackBReadinessPair;
  checks: Array<{ key: string; label: string; status: "pass" | "warn" | "block"; detail: string }>;
  blockers: string[]; warnings: string[]; next_action: string; professional_review_required: boolean;
};

function auth(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

function absolute(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${frontendEnv.apiBaseUrl.replace(/\/+$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
}

export const trackBApi = {
  // SMART_ORGANIZER_INTAKE_V1
  inspectOrganizerPackage: (projectId:string, files:File[], token:string) => {
    const form=new FormData(); files.forEach((file)=>form.append("files",file));
    return apiClient.request<TrackBOrganizerIntakeReport>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/track-b/organizer-intake/inspect`,
      {method:"POST",headers:auth(token),body:form},
    );
  },


  // SMART_ORGANIZER_PHASE2D1_FRONTEND_API
  discoverOrganizerSiteCandidates: (projectId:string, files:File[], token:string) => {
    const form=new FormData(); files.forEach((file)=>form.append("files",file));
    return apiClient.request<TrackBOrganizerSiteDiscovery>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/track-b/organizer-intake/site-candidates`,
      {method:"POST",headers:auth(token),body:form},
    );
  },

  uploadOrganizerSiteBoundary: (projectId:string, siteName:string, file:File, userConfirmed:boolean, token:string) => {
    const form=new FormData();
    form.append("site_name",siteName); form.append("user_confirmed",String(userConfirmed)); form.append("file",file);
    return apiClient.request<TrackBOrganizerSiteResolution>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/track-b/organizer-intake/site-resolution/upload`,
      {method:"POST",headers:auth(token),body:form},
    );
  },

  planOrganizerImport: (
    projectId:string,
    input:{siteName:string;siteGeometry:Record<string,unknown>;siteSourceRef:string;files:File[];userConfirmed:boolean},
    token:string,
  ) => {
    const form=new FormData();
    form.append("site_name",input.siteName);
    form.append("site_geometry_json",JSON.stringify(input.siteGeometry));
    form.append("site_source_ref",input.siteSourceRef);
    form.append("user_confirmed",String(input.userConfirmed));
    input.files.forEach((file)=>form.append("files",file));
    return apiClient.request<TrackBOrganizerImportPlan>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/track-b/organizer-intake/import-plan`,
      {method:"POST",headers:auth(token),body:form},
    );
  },

  importOrganizerPackage: (
    projectId:string,
    input:{
      siteName:string;siteGeometry:Record<string,unknown>;siteSourceRef:string;
      roleAssignments:Record<string,string>;files:File[];userConfirmed:boolean;
      allowInvalidGeometrySkip:boolean;executePersistent:boolean;
    },
    token:string,
  ) => {
    const form=new FormData();
    form.append("site_name",input.siteName);
    form.append("site_geometry_json",JSON.stringify(input.siteGeometry));
    form.append("site_source_ref",input.siteSourceRef);
    form.append("user_confirmed",String(input.userConfirmed));
    form.append("role_assignments_json",JSON.stringify(input.roleAssignments));
    form.append("allow_invalid_geometry_skip",String(input.allowInvalidGeometrySkip));
    form.append("execute_persistent",String(input.executePersistent));
    input.files.forEach((file)=>form.append("files",file));
    return apiClient.request<TrackBOrganizerImportAllResponse>(
      `/api/v1/projects/${encodeURIComponent(projectId)}/track-b/organizer-intake/import-all`,
      {method:"POST",headers:auth(token),body:form},
    );
  },

  readiness: (projectId: string, token: string) =>
    apiClient.get<TrackBReadiness>(`/api/v1/projects/${encodeURIComponent(projectId)}/track-b/readiness`, { headers: auth(token) }),

  list: (projectId: string, token: string) =>
    apiClient.get<TrackBDataset[]>(`/api/v1/projects/${encodeURIComponent(projectId)}/track-b/datasets`, {
      headers: auth(token),
    }),

  upload: (projectId: string, form: FormData, token: string) =>
    apiClient.request<TrackBDataset>(`/api/v1/projects/${encodeURIComponent(projectId)}/track-b/datasets/upload`, {
      method: "POST",
      headers: auth(token),
      body: form,
    }),

  uploadBundle: (projectId: string, form: FormData, token: string) =>
    apiClient.request<TrackBDataset>(`/api/v1/projects/${encodeURIComponent(projectId)}/track-b/datasets/bundle`, {
      method: "POST", headers: auth(token), body: form,
    }),

  uploadSentinelArchive: (projectId: string, form: FormData, token: string) =>
    apiClient.request<TrackBDataset>(`/api/v1/projects/${encodeURIComponent(projectId)}/track-b/datasets/sentinel-archive`, {
      method: "POST", headers: auth(token), body: form,
    }),

  analyze: (
    projectId: string,
    payload: {
      site_id: string;
      before_raster_id: string;
      after_raster_id: string;
      mode: "auto" | "ndvi" | "ndwi" | "ndbi" | "spectral" | "classified";
      absolute_delta_threshold: number;
      minimum_usable_coverage_percent: number;
    },
    token: string,
  ) =>
    apiClient.request<TrackBAnalysis>(`/api/v1/projects/${encodeURIComponent(projectId)}/track-b/analyze`, {
      method: "POST",
      headers: { ...auth(token), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  interpret: (projectId: string, analysisId: string, token: string) =>
    apiClient.request<TrackBAIInterpretation>(`/api/v1/projects/${encodeURIComponent(projectId)}/track-b/analyses/${encodeURIComponent(analysisId)}/ai-interpret`, {
      method: "POST", headers: auth(token),
    }),

  decisionWorkspace: (projectId: string, analysisId: string, plannerQuestion: string, token: string) =>
    apiClient.request<TrackBPlannerDecision>(`/api/v1/projects/${encodeURIComponent(projectId)}/track-b/analyses/${encodeURIComponent(analysisId)}/decision-workspace`, {
      method: "POST",
      headers: { ...auth(token), "Content-Type": "application/json" },
      body: JSON.stringify({ planner_question: plannerQuestion.trim() || null }),
    }),


  runHackathonWorkflow: (projectId: string, payload: { mode: "auto" | "ndvi" | "ndwi" | "ndbi" | "spectral" | "classified"; absolute_delta_threshold: number; minimum_usable_coverage_percent: number; planner_question: string | null }, token: string) =>
    apiClient.request<TrackBWorkflow>(`/api/v1/projects/${encodeURIComponent(projectId)}/track-b/workflow/hackathon-run`, {
      method: "POST",
      headers: { ...auth(token), "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  fetchGeoJson: async (url: string, token: string) => {
    const response = await fetch(absolute(url), { headers: auth(token) });
    if (!response.ok) throw new Error(`Unable to load change geometry (${response.status}).`);
    return response.json() as Promise<GeoJSON.FeatureCollection>;
  },

  fetchReport: async (url: string, token: string) => {
    const response = await fetch(absolute(url), { headers: auth(token) });
    if (!response.ok) throw new Error(`Unable to compose Track B report (${response.status}).`);
    return response.blob();
  },

  fetchPreview: async (projectId: string, rasterId: string, token: string) => {
    const response = await fetch(absolute(`/api/v1/projects/${encodeURIComponent(projectId)}/track-b/datasets/${encodeURIComponent(rasterId)}/preview.png`), { headers: auth(token) });
    if (!response.ok) throw new Error(`Unable to render dataset preview (${response.status}).`);
    return response.blob();
  },
};

