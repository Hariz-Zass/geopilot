import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SmartOrganizerControlledImport } from "./SmartOrganizerControlledImport";
import { sitesApi } from "../lib/api/sites";
import { trackBApi } from "../lib/api/trackB";

const compatibleTemporal = {
  phase: "GIS_TEMPORAL_PHASE_A" as const,
  database_writes: false as const,
  geometry_not_materialized: true as const,
  datasets: [],
  pair: { pair_status: "PAIR_COMPATIBLE", warnings: [], block_reasons: [], database_writes: false as const },
};

const blockedTemporal = { ...compatibleTemporal, pair: { ...compatibleTemporal.pair, pair_status: "PAIR_BLOCKED" } };

const boundedResult = {
  analysis_id: "analysis-1",
  dataset_pair: { before_dataset: "Selangor_Semasa_2023", after_dataset: "Selangor_Semasa_2024", before_year: 2023, after_year: 2024 },
  checksums: { before: "before-checksum", after: "after-checksum" },
  feature_counts: { before: 10, after: 11, staged_before: 10, staged_after: 11 },
  exact_match_count: 8,
  unchanged_count: 7,
  verified_reclassified_count: 1,
  verified_changed_area_ha: 1.25,
  unmatched_counts: { before: 2, after: 3 },
  unmatched_label: "NOT YET ANALYZED BY OVERLAP ENGINE",
  top_gtn1_transitions: [{ before_category: "Tanah Kosong", after_category: "Perumahan", feature_count: 1, measured_area_ha: 1.25 }],
  top_gtn2_transitions: [],
  top_gtn3_transitions: [],
  sample_verified_facts: [],
  runtime: { staging_before_seconds: 1, staging_after_seconds: 1, index_seconds: 1, exact_match_seconds: 1, total_runtime_seconds: 4 },
  matching_method: "EXACT_GEOMETRY" as const,
  confidence: "VERIFIED" as const,
  deterministic: true as const,
  status: "measured" as const,
  limitations: ["Phase B covers exact-geometry relationships only.", "Verified reclassified count is not every changed polygon."],
  source_provenance: {},
  staging_cleanup: {},
};

function mockInspection(temporal = compatibleTemporal) {
  vi.spyOn(trackBApi, "inspectOrganizerPackage").mockResolvedValue({
    phase: "inspect_only", database_writes: false, file_count: 1, supported_or_reviewable_count: 1,
    requires_confirmation_count: 0, blocker_count: 0, class_counts: {}, blockers: [], items: [], next_action: "ready",
  });
  vi.spyOn(trackBApi, "discoverOrganizerSiteCandidates").mockResolvedValue({
    phase: "site_discovery", database_writes: false, migration_required: false, candidate_count: 0,
    strong_candidate_count: 0, review_candidate_count: 0, empty_boundary_hint_count: 0, candidates: [],
    recommendation: { status: "review", logical_name: null, auto_create_site: false, user_confirmation_required: true }, next_action: "review",
  });
  vi.spyOn(trackBApi, "inspectGisTemporal").mockResolvedValue(temporal);
}

describe("SmartOrganizerControlledImport GIS temporal Slice 3", () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => cleanup());

  it("gates the action on a compatible pair and runs the current File[] bundle", async () => {
    const user = userEvent.setup();
    mockInspection();
    const analyze = vi.spyOn(trackBApi, "analyzeGisTemporalExact").mockResolvedValue(boundedResult);
    render(<SmartOrganizerControlledImport projectId="project-1" token="token-1" />);
    const file = new File(["organizer"], "Selangor_2023.zip", { type: "application/zip" });
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, file);
    await user.click(screen.getByRole("button", { name: /analyze organizer package/i }));
    await screen.findByText(/PAIR STATUS: PAIR COMPATIBLE/i);
    await user.click(screen.getByRole("button", { name: /run gis temporal analysis/i }));
    await waitFor(() => expect(analyze).toHaveBeenCalledWith("project-1", [file], "token-1"));
    expect(await screen.findByText(/gis temporal change intelligence/i)).toBeInTheDocument();
    expect(screen.getByText(/verified reclassified area among exact-geometry matches/i)).toBeInTheDocument();
    expect(screen.getByText(/exact-geometry analysis only/i)).toBeInTheDocument();
    expect(screen.getByText("NOT YET ANALYZED BY OVERLAP ENGINE")).toBeInTheDocument();
    expect(screen.getByText(/Tanah Kosong → Perumahan/i)).toBeInTheDocument();
  });

  it("keeps the run disabled for a blocked pair", async () => {
    const user = userEvent.setup();
    mockInspection(blockedTemporal);
    render(<SmartOrganizerControlledImport projectId="project-1" token="token-1" />);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, new File(["x"], "pair.zip"));
    await user.click(screen.getByRole("button", { name: /analyze organizer package/i }));
    const button = await screen.findByRole("button", { name: /run gis temporal analysis/i });
    expect(button).toBeDisabled();
  });

  it("hands only the bounded result to project-level temporal Ask GeoPilot", async () => {
    const user = userEvent.setup();
    mockInspection();
    vi.spyOn(trackBApi, "analyzeGisTemporalExact").mockResolvedValue(boundedResult);
    const active = vi.spyOn(sitesApi, "active");
    const ask = vi.spyOn(trackBApi, "askGisTemporal").mockResolvedValue({
      capability: "temporal_land_use_change",
      question: "What are the biggest verified land-use transitions?",
      status: "completed",
      evidence: [],
      synthesis: "Grounded answer.",
      provider_metadata: {},
      limitations: [],
    });
    render(<SmartOrganizerControlledImport projectId="project-1" token="token-1" />);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, new File(["x"], "pair.zip"));
    await user.click(screen.getByRole("button", { name: /analyze organizer package/i }));
    await user.click(await screen.findByRole("button", { name: /run gis temporal analysis/i }));
    await user.click(await screen.findByRole("button", { name: /ask geopilot about this result/i }));
    await waitFor(() => expect(ask).toHaveBeenCalled());
    expect(active).not.toHaveBeenCalled();
    expect(ask.mock.calls[0]?.[2]).toEqual(boundedResult);
    expect(ask.mock.calls[0]?.[2]).not.toHaveProperty("verified_reclassification_facts");
  });

  it("supports main-workspace presentation without duplicating the full result dashboard", async () => {
    const user = userEvent.setup();
    mockInspection();
    vi.spyOn(trackBApi, "analyzeGisTemporalExact").mockResolvedValue(boundedResult);
    const onTemporalResult = vi.fn();
    render(<SmartOrganizerControlledImport projectId="project-1" token="token-1" onTemporalResult={onTemporalResult} />);
    await user.upload(document.querySelector('input[type="file"]') as HTMLInputElement, new File(["x"], "pair.zip"));
    await user.click(screen.getByRole("button", { name: /analyze organizer package/i }));
    await user.click(await screen.findByRole("button", { name: /run gis temporal analysis/i }));
    await waitFor(() => expect(onTemporalResult).toHaveBeenCalledWith(boundedResult));
    expect(screen.getByText(/gis result ready/i)).toBeInTheDocument();
    expect(screen.queryByText(/top verified transitions/i)).not.toBeInTheDocument();
  });
});
