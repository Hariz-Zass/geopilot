import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GisTemporalResultDashboard } from "./GisTemporalResultDashboard";

const result = {
  analysis_id: "analysis-ui-1",
  project_id: "project-ui-1",
  dataset_pair: { before_dataset: "Selangor_Semasa_2023", after_dataset: "Selangor_Semasa_2024", before_year: 2023, after_year: 2024 },
  checksums: { before: "before-checksum", after: "after-checksum" },
  feature_counts: { before: 166175, after: 167640, staged_before: 166175, staged_after: 167640 },
  exact_match_count: 42614,
  unchanged_count: 41952,
  verified_reclassified_count: 662,
  verified_changed_area_ha: 861.496,
  unmatched_counts: { before: 123561, after: 125026 },
  unmatched_label: "NOT YET ANALYZED BY OVERLAP ENGINE",
  top_gtn1_transitions: [{ before_category: "Tanah Kosong", after_category: "Perumahan", feature_count: 210, measured_area_ha: 10.498 }],
  top_gtn2_transitions: [],
  top_gtn3_transitions: [],
  sample_verified_facts: [],
  runtime: { staging_before_seconds: 1, staging_after_seconds: 1, index_seconds: 1, exact_match_seconds: 1, total_runtime_seconds: 4 },
  matching_method: "EXACT_GEOMETRY" as const,
  confidence: "VERIFIED" as const,
  deterministic: true as const,
  status: "measured" as const,
  limitations: [
    "Phase B covers exact-geometry relationships only.",
    "Boundary-adjusted, split, merge, new, removed, and ambiguous relationships are not yet classified.",
    "Unmatched features remain NOT YET ANALYZED BY OVERLAP ENGINE.",
    "Verified changed area is not total Selangor temporal change.",
  ],
  source_provenance: { id: "analysis:analysis-ui-1" },
  staging_cleanup: {},
};

describe("GisTemporalResultDashboard", () => {
  afterEach(() => cleanup());

  it("renders the dynamic GIS result, bounded transitions, limitations, provenance, and Ask action", async () => {
    const user = userEvent.setup();
    const onAsk = vi.fn().mockResolvedValue({ status: "completed", synthesis: "### Key Finding\n\n**Grounded answer.**\n\n### Planning Insight\n\nInspect the verified transition.", evidence: [{ label: "Verified area", value: "861.496 ha" }], limitations: ["Exact-geometry evidence only."] });
    render(<GisTemporalResultDashboard result={result} onAsk={onAsk} />);

    expect(screen.getByRole("heading", { name: /gis temporal change intelligence/i })).toBeInTheDocument();
    expect(screen.getByText("Selangor_Semasa_2023")).toBeInTheDocument();
    expect(screen.getByText("Selangor_Semasa_2024")).toBeInTheDocument();
    expect(screen.getByText("42,614")).toBeInTheDocument();
    expect(screen.getByText("41,952")).toBeInTheDocument();
    expect(screen.getByText("662")).toBeInTheDocument();
    expect(screen.getByText("861.496")).toBeInTheDocument();
    expect(screen.getByText(/Tanah Kosong.*Perumahan/i)).toBeInTheDocument();
    expect(screen.getByText(/method & limitations/i)).toBeInTheDocument();
    expect(screen.getByText(/Boundary-adjusted, split, merge/i)).toBeInTheDocument();
    expect(screen.getByText("analysis:analysis-ui-1")).toBeInTheDocument();
    expect(screen.queryByText(/raster \/ satellite temporal metrics/i)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /ask geopilot about this result/i }));
    expect(onAsk).toHaveBeenCalledWith("What are the biggest verified land-use transitions?");
    expect(await screen.findByText("Grounded answer.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Key Finding" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Planning Insight" })).toBeInTheDocument();
    expect(screen.getByText("Supporting Evidence")).toBeInTheDocument();
    expect(screen.getByText("Evidence Boundary")).toBeInTheDocument();
    expect(screen.queryByText("### Key Finding")).not.toBeInTheDocument();
    expect(screen.queryByText("**Grounded answer.**")).not.toBeInTheDocument();
  });

  it("supports suggested shortcuts and free-text grounded questions", async () => {
    const user = userEvent.setup();
    const onAsk = vi.fn().mockResolvedValue({ status: "completed", synthesis: "Answer", evidence: [], limitations: [] });
    render(<GisTemporalResultDashboard result={result} onAsk={onAsk} />);

    const input = screen.getByRole("textbox", { name: /free-text gis question/i });
    await user.clear(input);
    await user.type(input, "Which verified area should I inspect first?");
    await user.click(screen.getByRole("button", { name: /ask geopilot about this result/i }));

    expect(onAsk).toHaveBeenCalledWith("Which verified area should I inspect first?");
  });
});
