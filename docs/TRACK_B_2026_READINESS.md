# GeoPilot AI — PLAN-Ai Hackathon 2026 Track B Readiness

## Competition basis

This Track B implementation is designed against the organizer requirements supplied by the project owner:

- Geospatial & Satellite AI Challenge.
- Two locations: one urban and one rural.
- Temporal data: minimum two images per location.
- Both raw and processed data may be supplied.
- Sentinel open-source data may be supplied as additional organizer evidence.
- During the hackathon, analysis must use organizer-supplied data only; outside data is not permitted.

## Closed-evidence Track B architecture

Track B is intentionally separated from public satellite acquisition code. The Track B API accepts only authenticated organizer uploads and persists immutable SHA-256 lineage.

`TRACK_B_COMPETITION_MODE=true` is the default. Track B analysis rejects raster records that are not marked `organizer_supplied_only`.

## Supported organizer material

### Processed / multiband raster

- GeoTIFF `.tif` / `.tiff`
- JPEG 2000 `.jp2` when supported by GDAL `JP2OpenJPEG`
- Single-band classified rasters
- Multiband processed rasters
- Explicit band-name override

### Raw Sentinel material

- Multiple single-band GeoTIFF/JP2 assets supplied as a band bundle.
- Sentinel ZIP / SAFE-like archives. The importer searches organizer archives for B02, B03, B04, B08, B11 and SCL assets.
- Mixed Sentinel resolutions are supported. Required bands are aligned server-side before index calculation.
- Common aliases such as `red`, `nir`, `swir1`, `B4`, and `B8` normalize to controlled Sentinel band IDs.

## Temporal engines

- `auto`: selects the strongest deterministic engine supported by the pair.
- `ndvi`: B08/B04 vegetation-index change.
- `ndwi`: B03/B08 water-index change.
- `ndbi`: B11/B08 built-up-index change.
- `spectral`: normalized multiband spectral distance for common bands.
- `classified`: categorical before/after class change for processed single-band products.

The LLM never calculates authoritative raster measurements. Rasterio/Numpy perform measurements; AI may only interpret validated evidence.

## Spatial safety

- Analysis is project and Site scoped.
- Site geometry is server-owned EPSG:4326 evidence and is projected onto the raster grid.
- The reported changed percentage uses valid pixels inside the selected Site, not the entire source tile.
- Changed area is calculated from projected pixel size. Geographic rasters use average geodesic pixel area and disclose that limitation.
- Before/after imagery with different grids or CRS is reprojected/resampled on the server.
- Processed categorical data uses nearest-neighbour alignment.

## Sentinel quality handling

When SCL is supplied, GeoPilot masks Sentinel classes associated with no-data, saturated pixels, cloud shadow, medium/high cloud, cirrus and snow/ice. Without SCL, quality masking is limited to organizer raster validity/nodata evidence and the limitation is disclosed.

## Large-scene safety

Raw Sentinel scenes may be very large. `TRACK_B_MAX_ANALYSIS_PIXELS` controls the analysis grid memory ceiling (default 16 million pixels). When the ceiling is applied, GeoPilot records the original and analysis-grid dimensions in the result limitations. The change-area calculation uses the resampled grid transform.

## Outputs

Each temporal run produces:

- measured changed pixel count and percentage;
- usable Site coverage percentage;
- changed area in hectares when CRS permits;
- index means for NDVI/NDWI/NDBI;
- immutable before/after raster checksums;
- Site geometry hash and revision;
- GeoTIFF change mask;
- WGS84 GeoJSON change regions for map display;
- a closed-evidence PDF report;
- explicit professional-review limitations.

## Interface

`/projects/{project_id}/track-b` provides the GeoPilot Temporal Command Center:

- futuristic dark geospatial workspace;
- Closed Evidence Mode indicator;
- urban/rural organizer dataset ingestion;
- processed raster, raw band bundle and Sentinel ZIP modes;
- T1/T2 quicklook previews;
- temporal-engine selection;
- deterministic change map;
- measurement cards;
- evidence lineage;
- professional-review boundary;
- evidence PDF generation.

No external basemap is requested by the Track B map. The change layer is rendered on a local dark spatial canvas so the competition workflow does not need outside map data.

## Acceptance gate before competition day

Implementation readiness is separate from real organizer-data acceptance. When the official files are released, perform this gate for BOTH urban and rural locations:

1. Ingest organizer raw data.
2. Ingest organizer processed data.
3. Verify CRS, dimensions, bounds, bands and acquisition dates.
4. Confirm at least T1 and T2 for each location.
5. Run `auto`, then the challenge-relevant explicit engine.
6. Confirm usable Site coverage satisfies the configured threshold.
7. Visually compare generated change regions with organizer imagery.
8. Open the evidence PDF and verify checksums, method and limitations.
9. Confirm Track B capabilities reports GeoTIFF and JP2 support.
10. Run backend and frontend test suites in the competition machine's Docker environment.

Only after official data passes this gate should the system be described as real-data accepted for the challenge.

## Grounded AI Planning Copilot

Track B now includes an evidence-bounded AI interpretation endpoint after deterministic temporal analysis. The copilot receives only the persisted organizer-supplied raster measurements, Site lineage, method and limitations. It is prohibited by prompt and server validation from inventing numeric measurements, external planning facts, statutory conclusions or causal claims. Provider failover uses the existing Ollama -> OpenAI strategy. AI output is structured into planner problem, evidence-linked insights, planning relevance, recommended action queue, caveats and confidence. Deterministic raster measurements remain authoritative.

## Urban vs Rural AI Intelligence
GeoPilot now supports a closed-evidence urban-versus-rural AI comparison endpoint. Each temporal analysis persists its organizer-provided location type and data stage. The comparison gate requires one explicitly urban analysis and one explicitly rural analysis, rejects evidence outside the organizer/server-owned boundary, and applies the same numeric-grounding guard used by the single-analysis copilot. The AI is instructed to translate measured differences into planner priorities and verification actions without asserting unsupported causes or statutory conclusions.

## AI Planner Decision Workspace

GeoPilot now converts one deterministic temporal analysis into an auditable decision brief:

`Issue → Evidence → non-statutory triage priority → Planning implication → Planner action → Verification need → Limitations`.

A planner may provide a question/problem statement, but the AI remains restricted to organizer-derived evidence. Priority is explicitly a workflow triage label, never a statutory severity, compliance result, approval, or legal conclusion. Numeric hallucination guards and controlled evidence references apply to the decision workspace as they do to the base Track B AI interpretation.

## Hackathon Simulation Mode
A one-click `/workflow/hackathon-run` mission now auto-selects the newest viable organizer-supplied Urban and Rural before/after pairs sharing a Site and data stage. It runs deterministic temporal analysis first, then bounded grounded AI interpretation, planner decision briefs, and Urban/Rural comparison. AI provider failure returns a `partial` mission while preserving valid deterministic outputs; external evidence remains prohibited.


## Competition acceptance gate (v7)
GeoPilot now exposes `GET /api/v1/projects/{project_id}/track-b/readiness` as a server-side competition preflight. The gate verifies closed-evidence mode, GeoTIFF/JP2 runtime support, immutable local organizer artifacts, checksum lineage, same-Site/same-stage Urban and Rural T1/T2 pairs, temporal ordering, and planning-AI configuration. It returns `ready`, `partial`, or `blocked` with explicit blockers and the next action.

Synthetic QA fixtures are explicitly excluded from mission pairing and competition readiness. They exist only to exercise ingestion/analysis plumbing before organizer data is released.

### Local QA fixture generator
Run `python scripts/generate-track-b-demo-fixtures.py` from the repository root (with backend dependencies available). It creates four small B04/B08 GeoTIFF scenes under `artifacts/track_b_demo_fixtures/` plus a warning manifest. Every fixture is labelled **DEMO ONLY — NOT ORGANIZER EVIDENCE** and must not be used in a competition submission.
