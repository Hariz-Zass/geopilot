import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const pageSource = readFileSync(resolve(process.cwd(), "src/pages/TrackBWorkspacePage.tsx"), "utf-8");
const stylesSource = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf-8");

function between(start: string, end: string) {
  const startIndex = pageSource.indexOf(start);
  const endIndex = pageSource.indexOf(end, startIndex);
  return pageSource.slice(startIndex, endIndex);
}

describe("Track B GIS temporal dashboard layout contract", () => {
  it("renders a bounded workflow sidebar beside one right-side main column", () => {
    const grid = between('<div className={`trackb-grid', '<section className="planner-decision-workspace hackathon-simulation">');
    const sidebarStart = grid.indexOf('<aside className="trackb-side-panel">');
    const sidebarEnd = grid.indexOf("</aside>", sidebarStart);
    const mainColumn = grid.indexOf('<div className="trackb-main-column">');
    const mainEnd = grid.lastIndexOf("</main>");
    const dashboard = grid.indexOf("<GisTemporalResultDashboard");

    expect(mainColumn).toBeGreaterThan(sidebarEnd);
    expect(dashboard).toBeGreaterThan(mainColumn);
    expect(dashboard).toBeLessThan(mainEnd);
    expect(grid.slice(sidebarStart, sidebarEnd)).not.toContain("GisTemporalResultDashboard");
    expect(grid.slice(mainColumn, mainEnd)).toContain('className="trackb-workspace-tabs"');
  });

  it("keeps the root grid and main column width-safe without placement hacks", () => {
    const rootStyles = stylesSource.match(/\.trackb-grid \{[\s\S]*?grid-template-columns: minmax\(320px, 360px\) minmax\(0, 1fr\);[\s\S]*?\}/)?.[0] ?? "";
    const mainStyles = stylesSource.match(/\.trackb-main-column \{[\s\S]*?\}/)?.[0] ?? "";
    expect(rootStyles).toContain("minmax(320px, 360px)");
    expect(rootStyles).toContain("minmax(0, 1fr)");
    expect(mainStyles).toContain("min-width: 0");
    expect(stylesSource).toContain("position: sticky");
    expect(stylesSource).not.toMatch(/\.trackb-result-slot[\s\S]{0,250}(position:\s*(absolute|fixed)|translateX|margin-left:\s*-)/);
  });

  it("keeps live GIS state, tab behavior, and raster-only context separate", () => {
    expect(pageSource).toContain("onTemporalResult={handleTemporalResult}");
    expect(pageSource).toContain('setWorkspaceTab("gis")');
    expect(pageSource).toContain('setWorkspaceTab("ask")');
    expect(pageSource).toContain('view={workspaceTab === "ask" ? "ask" : workspaceTab === "evidence" ? "evidence" : "gis"}');
    expect(pageSource).toContain("RASTER / SATELLITE TEMPORAL METRICS");
    expect(pageSource).toContain('workspaceTab === "satellite" && result');
    expect(pageSource).toContain("SATELLITE CHANGE MAP");
    expect(pageSource).toContain("Cyan overlay/polygons = detected spectral-change regions");
    expect(pageSource).toContain("Spectral change is measured evidence and does not by itself prove land-use change or planning causation.");
    expect(pageSource).toContain("Measured GIS temporal evidence is available");
    expect(pageSource).toContain('className="trackb-workspace-tabs"');
    expect(pageSource).toContain("<GisTemporalResultDashboard");
  });

  it("keeps the dashboard width-safe", () => {
    const dashboardStyles = stylesSource.match(/\.gis-temporal-result-dashboard \{[\s\S]*?\}/)?.[0] ?? "";
    expect(dashboardStyles).toMatch(/min-width:\s*0/);
    expect(dashboardStyles).toMatch(/width:\s*100%/);
  });
});
