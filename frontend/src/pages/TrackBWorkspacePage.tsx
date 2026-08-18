import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Map as MapLibreMap, NavigationControl, LngLatBounds, type GeoJSONSource } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Link, Navigate, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ApiError } from "../lib/api/errors";
import { sitesApi, type SiteResponse } from "../lib/api/sites";
import { trackBApi, type TrackBAIInterpretation, type TrackBAnalysis, type TrackBDataset, type TrackBOrganizerIntakeReport, type TrackBPlannerDecision, type TrackBWorkflow, type TrackBReadiness } from "../lib/api/trackB";
import { type PlanningRunResponse } from "../lib/api/planningRuns";
import { getSessionAccessToken } from "../lib/auth/session";
import { SmartOrganizerControlledImport } from "../components/SmartOrganizerControlledImport";

function label(value: unknown) {
  return typeof value === "string" ? value : "—";
}

function GroundedMarkdown({ value }: { value: string }) {
  return (
    <div className="grounded-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{value}</ReactMarkdown>
    </div>
  );
}

function TrackBMap({ geojson }: { geojson?: GeoJSON.FeatureCollection }) {
  const node = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);

  useEffect(() => {
    if (!node.current || map.current) return;
    map.current = new MapLibreMap({
      container: node.current,
      // TRACKB_CONTEXT_BASEMAP_V1
      // Visual context only. Not used by analysis, evidence lineage or AI grounding.
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [101.7, 3.05],
      zoom: 8,
      attributionControl: {},
    });
    map.current.addControl(new NavigationControl({ visualizePitch: true }), "bottom-right");
    return () => { map.current?.remove(); map.current = null; };
  }, []);

  useEffect(() => {
    const current = map.current;
    if (!current || !geojson) return;
    const apply = () => {
      if (!current.getSource("track-b-change")) {
        current.addSource("track-b-change", { type: "geojson", data: geojson });
        current.addLayer({
          id: "track-b-change-fill",
          type: "fill",
          source: "track-b-change",
          paint: { "fill-color": "#26f6d1", "fill-opacity": 0.36 },
        });
        current.addLayer({
          id: "track-b-change-line",
          type: "line",
          source: "track-b-change",
          paint: { "line-color": "#b5fff3", "line-width": 1.4 },
        });
      } else {
        (current.getSource("track-b-change") as GeoJSONSource).setData(geojson);
      }
      const coords: [number, number][] = [];
      geojson.features.forEach((feature) => {
        const geometry = feature.geometry;
        if (geometry.type === "Polygon") geometry.coordinates[0]?.forEach((c) => coords.push(c as [number, number]));
        if (geometry.type === "MultiPolygon") geometry.coordinates.forEach((p) => p[0]?.forEach((c) => coords.push(c as [number, number])));
      });
      if (coords.length) {
        const bounds = coords.reduce((b, c) => b.extend(c), new LngLatBounds(coords[0], coords[0]));
        current.fitBounds(bounds, { padding: 52, maxZoom: 14, duration: 750 });
      }
    };
    current.loaded() ? apply() : current.once("load", apply);
  }, [geojson]);

  return <div ref={node} className="trackb-map" aria-label="Temporal change map" />;
}

export function TrackBWorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const token = getSessionAccessToken();
  const [sites, setSites] = useState<SiteResponse[]>([]);
  const [datasets, setDatasets] = useState<TrackBDataset[]>([]);
  const [siteId, setSiteId] = useState("");
  const [autoCreateSite, setAutoCreateSite] = useState(false);
  const [beforeId, setBeforeId] = useState("");
  const [afterId, setAfterId] = useState("");
  const [mode, setMode] = useState<"auto" | "ndvi" | "ndwi" | "ndbi" | "spectral" | "classified">("auto");
  const [threshold, setThreshold] = useState(0.2);
  const [result, setResult] = useState<TrackBAnalysis>();
  const [geojson, setGeojson] = useState<GeoJSON.FeatureCollection>();
  const [aiInsight, setAiInsight] = useState<TrackBAIInterpretation>();
  const [decision, setDecision] = useState<TrackBPlannerDecision>();
  // DECISION_WORKSPACE_TERRAIN_ROUTER_V1
  const [terrainPlanningRun, setTerrainPlanningRun] =
    useState<PlanningRunResponse>();
  const [plannerQuestion, setPlannerQuestion] = useState("");
  const [hackathonWorkflow, setHackathonWorkflow] = useState<TrackBWorkflow>();
  const [missionMapView, setMissionMapView] = useState<"urban" | "rural">("urban");
  const [hackathonBusy, setHackathonBusy] = useState(false);
  const [judgeMode, setJudgeMode] = useState(false);
  const [serverReadiness, setServerReadiness] = useState<TrackBReadiness>();
  const [aiBusy, setAiBusy] = useState(false);
  const [beforePreview, setBeforePreview] = useState<string>();
  const [afterPreview, setAfterPreview] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [ingestMode, setIngestMode] = useState<"processed" | "bundle" | "sentinel">("processed");
  // SMART_ORGANIZER_INTAKE_V1
  const [intakeReport, setIntakeReport] = useState<TrackBOrganizerIntakeReport>();
  const [intakeBusy, setIntakeBusy] = useState(false);

  const load = useCallback(async () => {
    if (!projectId || !token) return;
    setError(undefined);
    try {
      const [nextSites, nextDatasets, nextReadiness] = await Promise.all([sitesApi.list(projectId, token), trackBApi.list(projectId, token), trackBApi.readiness(projectId, token)]);
      setSites(nextSites);
      setDatasets(nextDatasets);
      setServerReadiness(nextReadiness);
      const active = nextSites.find((s) => s.is_active && !s.is_archived) ?? nextSites[0];
      if (active && !siteId && !autoCreateSite) setSiteId(active.id);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Unable to load Track B workspace.");
    }
  }, [projectId, token, siteId, autoCreateSite]);

  useEffect(() => { void load(); }, [load]);

  const eligible = useMemo(() => datasets.filter((d) => !siteId || !d.site_id || d.site_id === siteId), [datasets, siteId]);
  const missionReadiness = useMemo(() => {
    const eligibleEvidence = datasets.filter((d) => Boolean(d.site_id) && Boolean(d.checksum_sha256) && Boolean(d.source_uri));
    const pairReady = (location: "urban" | "rural") => {
      const scoped = eligibleEvidence.filter((d) => d.provenance.location_type === location);
      return scoped.some((before) => before.provenance.temporal_role === "before" && scoped.some((after) => after.provenance.temporal_role === "after" && after.site_id === before.site_id && after.provenance.data_stage === before.provenance.data_stage));
    };
    const urban = pairReady("urban");
    const rural = pairReady("rural");
    return { urban, rural, organizerCount: eligibleEvidence.length, ready: urban && rural };
  }, [datasets]);

  useEffect(() => {
    let cancelled = false; let url: string | undefined;
    if (!beforeId || !projectId || !token) { setBeforePreview(undefined); return; }
    void trackBApi.fetchPreview(projectId, beforeId, token).then((blob) => { if (!cancelled) { url = URL.createObjectURL(blob); setBeforePreview(url); } }).catch(() => setBeforePreview(undefined));
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [beforeId, projectId, token]);

  useEffect(() => {
    let cancelled = false; let url: string | undefined;
    if (!afterId || !projectId || !token) { setAfterPreview(undefined); return; }
    void trackBApi.fetchPreview(projectId, afterId, token).then((blob) => { if (!cancelled) { url = URL.createObjectURL(blob); setAfterPreview(url); } }).catch(() => setAfterPreview(undefined));
    return () => { cancelled = true; if (url) URL.revokeObjectURL(url); };
  }, [afterId, projectId, token]);

  if (!token) return <Navigate to="/login" replace />;
  // TRACKB_MISSION_MAP_WIRING_V2
  const showMissionAnalysis = async (
    workflow: TrackBWorkflow,
    view: "urban" | "rural",
  ) => {
    if (!token) return;

    const analysis = view === "urban"
      ? workflow.urban_analysis
      : workflow.rural_analysis;
    const interpretation = view === "urban"
      ? workflow.urban_ai
      : workflow.rural_ai;
    const plannerDecision = view === "urban"
      ? workflow.urban_decision
      : workflow.rural_decision;

    setMissionMapView(view);
    setResult(analysis);
    setAiInsight(interpretation ?? undefined);
    setDecision(plannerDecision ?? undefined);
    setSiteId(analysis.site_id);
    setBeforeId(analysis.before_raster_id);
    setAfterId(analysis.after_raster_id);

    if (analysis.change_geojson_url) {
      const nextGeoJson = await trackBApi.fetchGeoJson(
        analysis.change_geojson_url,
        token,
      );
      setGeojson(nextGeoJson);
    } else {
      setGeojson(undefined);
    }
  };

  const runHackathonSimulation = async () => {
    if (!projectId || !token) return;

    setHackathonBusy(true);
    setError(undefined);

    try {
      const workflow = await trackBApi.runHackathonWorkflow(
        projectId,
        {
          mode,
          absolute_delta_threshold: threshold,
          minimum_usable_coverage_percent: 90,
          planner_question: plannerQuestion.trim() || null,
        },
        token,
      );

      setHackathonWorkflow(workflow);

      // Default judge/demo map to the Urban mission result.
      await showMissionAnalysis(workflow, "urban");
    } catch (cause) {
      setError(
        cause instanceof ApiError
          ? cause.message
          : cause instanceof Error
            ? cause.message
            : "Hackathon workflow failed.",
      );
    } finally {
      setHackathonBusy(false);
    }
  };
  if (!projectId) return <Navigate to="/projects" replace />;

  // SMART_ORGANIZER_INTAKE_V1
  async function inspectOrganizerPackage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId || !token) { setError("Authentication is required."); return; }
    const form=new FormData(event.currentTarget);
    const files=form.getAll("organizer_files").filter((v):v is File=>v instanceof File && v.size>0);
    if (!files.length) { setError("Choose one or more organizer files."); return; }
    setIntakeBusy(true); setError(undefined);
    try { setIntakeReport(await trackBApi.inspectOrganizerPackage(projectId,files,token)); }
    catch(caught){ setError(caught instanceof ApiError ? caught.message : caught instanceof Error ? caught.message : "Organizer inspection failed."); }
    finally { setIntakeBusy(false); }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!projectId || !token) {
      setError("Authentication is required.");
      return;
    }

    const formEl = event.currentTarget;
    const form = new FormData(formEl);

    if (autoCreateSite) {
      form.delete("site_id");
      form.set("auto_create_site", "true");
    } else {
      form.delete("auto_create_site");
      if (siteId) form.set("site_id", siteId);
    }

    setBusy(true); setError(undefined);
    try {
      let created: TrackBDataset;

      if (ingestMode === "bundle") created = await trackBApi.uploadBundle(projectId, form, token);
      else if (ingestMode === "sentinel") created = await trackBApi.uploadSentinelArchive(projectId, form, token);
      else created = await trackBApi.upload(projectId, form, token);

      formEl.reset();

      if (autoCreateSite && created.site_id) {
        setSiteId(created.site_id);
      }

      setAutoCreateSite(false);
      await load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Dataset ingestion failed.");
    } finally { setBusy(false); }
  }

  async function analyze() {
    if (!projectId || !token) {
      setError("Authentication is required.");
      return;
    }

    if (!siteId || !beforeId || !afterId) { setError("Choose a Site, before dataset and after dataset."); return; }
    setBusy(true); setError(undefined); setGeojson(undefined); setAiInsight(undefined); setDecision(undefined);
    try {
      const next = await trackBApi.analyze(projectId, {
        site_id: siteId,
        before_raster_id: beforeId,
        after_raster_id: afterId,
        mode,
        absolute_delta_threshold: threshold,
        minimum_usable_coverage_percent: 90,
      }, token);
      setResult(next);

      const changeGeoJsonUrl = next.change_geojson_url;
      if (changeGeoJsonUrl) {
        setGeojson(await trackBApi.fetchGeoJson(changeGeoJsonUrl, token));
      }
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : caught instanceof Error ? caught.message : "Temporal analysis failed.");
    } finally { setBusy(false); }
  }

  async function runAIInterpretation() {
    if (!projectId || !token || !result) return;
    setAiBusy(true); setError(undefined);
    try {
      setAiInsight(await trackBApi.interpret(projectId, result.analysis_id, token));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : caught instanceof Error ? caught.message : "AI interpretation failed.");
    } finally { setAiBusy(false); }
  }

  function isTerrainMeasurementQuestion(value: string) {
    const q = value.toLocaleLowerCase().replace(/\s+/g, " ").trim();

    const terrainTerms = [
      "slope", "gradient", "terrain", "topography", "topographic",
      "elevation", "altitude", "contour", "dem", "kecerunan",
      "cerun", "elevasi", "aras tanah", "kontur", "topografi",
    ];
    const measurementTerms = [
      "berapa", "what is", "highest", "lowest", "maximum", "minimum",
      "max ", "min ", "average", "mean", "purata", "tertinggi",
      "terendah", "nilai", "calculate", "measure", "ukur", "kira",
      "site", "tapak", "kawasan",
    ];
    const policyTerms = [
      "policy", "standard", "guideline", "requirement", "allowed",
      "permitted", "statutory", "gpp", "rfn", "rsn", "rkk",
      "rancangan tempatan", "garis panduan", "piawaian", "syarat",
      "dibenarkan", "had",
    ];

    const contains = (terms: string[]) =>
      terms.some((term) => q.includes(term));

    return contains(terrainTerms) &&
      contains(measurementTerms) &&
      !contains(policyTerms);
  }

  async function runPlannerDecision() {
    if (!projectId || !token || !result) {
      setError("Decision workspace is not ready: Project, authentication, or temporal analysis context is missing.");
      return;
    }

    if (!plannerQuestion.trim()) {
      setError("Enter a planner question before building the decision brief.");
      return;
    }

    setAiBusy(true);
    setError(undefined);

    try {
      // TRACKB_SERVER_ROUTER_FRONTEND_V1_2
      // Backend V2 is authoritative:
      // terrain question -> terrain.site_summary
      // temporal question -> Track B grounded decision flow
      const nextDecision = await trackBApi.decisionWorkspace(
        projectId,
        result.analysis_id,
        plannerQuestion.trim(),
        token,
      );

      setDecision(nextDecision);
      setTerrainPlanningRun(undefined);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : caught instanceof Error
            ? caught.message
            : "Planner decision workspace failed.",
      );
    } finally {
      setAiBusy(false);
    }
  }

  async function openEvidenceReport() {
    if (!token) {
      setError("Authentication is required.");
      return;
    }

    const reportUrl = result?.report_url;
    if (!reportUrl) return;

    setBusy(true); setError(undefined);
    try {
      const blob = await trackBApi.fetchReport(reportUrl, token);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = "GeoPilot_TrackB_Evidence_Report.pdf"; anchor.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to create evidence report.");
    } finally { setBusy(false); }
  }

  return (
    <section className="trackb-command-center">
      <header className="trackb-hero">
        <div>
          <p className="trackb-kicker">PLAN-Ai Hackathon 2026 · Track B</p>
          <h1>GeoPilot <span>Temporal Command Center</span></h1>
          <p>Geospatial & Satellite AI workflow for provenance-controlled urban and rural temporal evidence.</p>
        </div>
        <div className="trackb-hero-actions"><button className={`judge-mode-toggle ${judgeMode ? "active" : ""}`} onClick={() => setJudgeMode((value) => !value)}>{judgeMode ? "Exit Judge View" : "Judge View"}</button></div>
      </header>

      <div className="trackb-toolbar">
        <label><span>Active Site</span><select value={siteId} onChange={(e) => setSiteId(e.target.value)}><option value="">Select Site</option>{sites.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
        <div className="trackb-mode-tabs"><button className={ingestMode === "processed" ? "active" : ""} onClick={() => setIngestMode("processed")}>Processed / multiband</button><button className={ingestMode === "bundle" ? "active" : ""} onClick={() => setIngestMode("bundle")}>Band bundle</button><button className={ingestMode === "sentinel" ? "active" : ""} onClick={() => setIngestMode("sentinel")}>Sentinel ZIP / SAFE</button></div>
        <Link className="ghost-link" to={`/projects/${projectId}`}>Project workspace</Link>
      </div>

      {judgeMode && <section className="judge-command-deck">
        <div className="judge-title"><span>JUDGE VIEW · DECISION INTELLIGENCE</span><h2>One screen. Measured evidence → planning action.</h2><p>GeoPilot separates deterministic satellite measurement from grounded AI reasoning so every recommendation remains traceable to organizer-supplied evidence.</p></div>
        <div className="judge-readiness">
          <article className={(serverReadiness?.urban.ready ?? missionReadiness.urban) ? "ready" : "blocked"}><small>URBAN PAIR</small><strong>{(serverReadiness?.urban.ready ?? missionReadiness.urban) ? "READY" : "MISSING"}</strong></article>
          <article className={(serverReadiness?.rural.ready ?? missionReadiness.rural) ? "ready" : "blocked"}><small>RURAL PAIR</small><strong>{(serverReadiness?.rural.ready ?? missionReadiness.rural) ? "READY" : "MISSING"}</strong></article>
          <article><small>ORGANIZER DATA</small><strong>{serverReadiness?.organizer_dataset_count ?? missionReadiness.organizerCount}</strong></article>
          <article className={hackathonWorkflow?.status === "complete" ? "ready" : ""}><small>MISSION</small><strong>{hackathonWorkflow?.status?.toUpperCase() ?? (missionReadiness.ready ? "READY TO RUN" : "WAITING")}</strong></article>
        </div>
        {hackathonWorkflow ? <div className="judge-results">
          <article><small>URBAN CHANGE</small><strong>{hackathonWorkflow.urban_analysis.changed_percentage.toFixed(2)}%</strong><span>{hackathonWorkflow.urban_analysis.changed_area_hectares != null ? `${hackathonWorkflow.urban_analysis.changed_area_hectares.toFixed(2)} ha` : "Area unavailable"}</span><p>{hackathonWorkflow.urban_decision?.decision_title ?? "Deterministic result available"}</p></article>
          <article><small>RURAL CHANGE</small><strong>{hackathonWorkflow.rural_analysis.changed_percentage.toFixed(2)}%</strong><span>{hackathonWorkflow.rural_analysis.changed_area_hectares != null ? `${hackathonWorkflow.rural_analysis.changed_area_hectares.toFixed(2)} ha` : "Area unavailable"}</span><p>{hackathonWorkflow.rural_decision?.decision_title ?? "Deterministic result available"}</p></article>
          <article className="judge-strategy"><small>AI PLANNING PRIORITY</small><h3>{hackathonWorkflow.comparison?.shared_planning_problem ?? "Grounded comparison unavailable"}</h3><p>{hackathonWorkflow.comparison?.strategic_summary ?? "Measured evidence remains valid even when the AI provider is unavailable."}</p><div className="ai-evidence-tags"><code>PROVENANCE_CONTROLLED</code><code>MEASUREMENT_FIRST</code><code>PRO_REVIEW</code></div></article>
        </div> : <div className="judge-empty"><strong>{missionReadiness.ready ? "Mission-ready evidence detected." : "Track B evidence is not mission-ready yet."}</strong><span>{missionReadiness.ready ? "Run the full Track B mission below to populate the judge decision deck." : "Register matching Urban and Rural T1/T2 evidence pairs with the same Site and data stage."}</span></div>}
      </section>}

      {serverReadiness && <section className={`acceptance-gate ${serverReadiness.status}`}>
        <div><span className="decision-kicker">COMPETITION ACCEPTANCE GATE</span><h2>{serverReadiness.status.toUpperCase()}</h2><p>{serverReadiness.next_action}</p></div>
        <div className="acceptance-checks">{serverReadiness.checks.map((check) => <article key={check.key} className={check.status}><strong>{check.status === "pass" ? "✓" : check.status === "warn" ? "!" : "×"} {check.label}</strong><span>{check.detail}</span></article>)}</div>
        {!!serverReadiness.blockers.length && <div className="acceptance-blockers"><strong>Blockers</strong>{serverReadiness.blockers.map((item) => <span key={item}>{item}</span>)}</div>}
      </section>}

      <div className={`trackb-grid ${judgeMode ? "judge-hide-workbench" : ""}`}>
        <aside className="trackb-side-panel">
          <div className="panel-heading"><span>01</span><div><strong>Evidence Ingestion</strong><small>GeoTIFF · TIFF · JP2</small></div></div>
          {/* SMART_ORGANIZER_PHASE2D1_FRONTEND */}
          <SmartOrganizerControlledImport
            projectId={projectId}
            token={token}
            onCommitted={load}
          />

          <section className="smart-intake">
  <div className="smart-intake-head"><div><span>SMART ORGANIZER INTAKE</span><strong>Inspect all challenge materials at once</strong><small>Inspect-only. No database writes until confirmation.</small></div><code>PHASE 1</code></div>
  <form className="smart-intake-form" onSubmit={inspectOrganizerPackage}>
    <label>Organizer files<input name="organizer_files" type="file" multiple accept=".tif,.tiff,.jp2,.zip,.geojson,.json,.pdf,.csv" required /></label>
    <button className="neon-button" disabled={intakeBusy}>{intakeBusy ? "Inspecting…" : "Inspect & classify package"}</button>
  </form>
  {intakeReport && <div className="smart-intake-report">
    <div className="smart-intake-summary"><span><strong>{intakeReport.file_count}</strong> files</span><span><strong>{intakeReport.supported_or_reviewable_count}</strong> recognized</span><span><strong>{intakeReport.requires_confirmation_count}</strong> confirm</span><span><strong>{intakeReport.blocker_count}</strong> blockers</span></div>
    <p>{intakeReport.next_action}</p>
    <div className="smart-intake-items">{intakeReport.items.map((item)=><article key={`${item.index}-${item.filename}`}><div><strong>{item.filename}</strong><small>{item.classification.replaceAll("_"," ")}</small></div><div className="smart-intake-tags"><code>{item.confidence.toUpperCase()}</code>{item.location_type&&<code>{item.location_type.toUpperCase()}</code>}{item.temporal_role&&<code>{item.temporal_role.toUpperCase()}</code>}{item.data_stage&&<code>{item.data_stage.toUpperCase()}</code>}{item.band_name&&<code>{item.band_name}</code>}{item.suggested_applicability_role&&<code>{item.suggested_applicability_role.toUpperCase()}</code>}{item.requires_confirmation&&<code className="confirm">CONFIRM</code>}</div>{!!item.issues.length&&<ul>{item.issues.map((issue)=><li key={issue}>{issue}</li>)}</ul>}</article>)}</div>
  </div>}
</section>
<div className="manual-ingestion-label"><span>MANUAL / FALLBACK INGESTION</span><small>Existing path preserved.</small></div>
<form className="trackb-form" onSubmit={upload}>
            <label>Name<input name="name" placeholder="Urban Sentinel T1" required /></label>
            <div className="two-col"><label>Location<select name="location_type" defaultValue="urban"><option value="urban">Urban</option><option value="rural">Rural</option></select></label><label>Time role<select name="temporal_role" defaultValue="before"><option value="before">T1 · Before</option><option value="after">T2 · After</option><option value="reference">Reference</option></select></label></div>
            <div className="two-col"><label>Stage<select name="data_stage" defaultValue={ingestMode === "processed" ? "processed" : "raw"}><option value="raw">Raw</option><option value="processed">Processed</option></select></label><label>Acquired<input name="acquisition_datetime" placeholder="2026-06-01T02:00:00Z" /></label></div>
            {ingestMode === "bundle" ? <><label>Band names<input name="band_names" placeholder="B02,B03,B04,B08,B11,SCL" required /></label><label>Band files<input name="files" type="file" accept=".tif,.tiff,.jp2" multiple required /></label></> : ingestMode === "sentinel" ? <label>Sentinel archive<input name="file" type="file" accept=".zip" required /></label> : <><label>Band names <small>(optional)</small><input name="band_names" placeholder="B02,B03,B04,B08" /></label><label>Raster<input name="file" type="file" accept=".tif,.tiff,.jp2" required /></label></>}
            <label className="trackb-check">
              <input
                name="auto_create_site"
                type="checkbox"
                value="true"
                checked={autoCreateSite}
                onChange={(e) => {
                  const enabled = e.target.checked;
                  setAutoCreateSite(enabled);
                  if (enabled) setSiteId("");
                }}
              />
              Auto-create challenge Site from raster extent
            </label>
            <button className="neon-button" disabled={busy}>{busy ? "Processing…" : "Ingest organizer evidence"}</button>
          </form>

          <div className="dataset-stack">
            <div className="panel-heading compact"><span>02</span><div><strong>Temporal Pair</strong><small>{eligible.length} datasets registered</small></div></div>
            <label>Before<select value={beforeId} onChange={(e) => setBeforeId(e.target.value)}><option value="">Select T1</option>{eligible.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
            <label>After<select value={afterId} onChange={(e) => setAfterId(e.target.value)}><option value="">Select T2</option>{eligible.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></label>
            <div className="two-col"><label>Engine<select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}><option value="auto">Auto detect</option><option value="ndvi">NDVI</option><option value="ndwi">NDWI</option><option value="ndbi">NDBI</option><option value="spectral">Spectral</option><option value="classified">Class change</option></select></label><label>Threshold<input type="number" step="0.01" min="0.01" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))} /></label></div>
            <button className="analysis-button" disabled={busy || !beforeId || !afterId} onClick={() => void analyze()}>{busy ? "Analyzing…" : "Run temporal intelligence"}</button>
          </div>
        </aside>

        <main className="trackb-main-panel">
          <div className="temporal-preview-strip">
            <article><div><span>T1 · BEFORE</span><small>{datasets.find((d) => d.id === beforeId)?.acquisition_datetime ?? "Select dataset"}</small></div>{beforePreview ? <img src={beforePreview} alt="Before raster quicklook" /> : <div className="preview-placeholder">T1</div>}</article>
            <div className="temporal-arrow"><span>→</span><small>temporal delta</small></div>
            <article><div><span>T2 · AFTER</span><small>{datasets.find((d) => d.id === afterId)?.acquisition_datetime ?? "Select dataset"}</small></div>{afterPreview ? <img src={afterPreview} alt="After raster quicklook" /> : <div className="preview-placeholder">T2</div>}</article>
          </div>
          <div className="map-frame">
            <div className="map-hud">
              <span>SPATIAL CHANGE LAYER</span>
              {hackathonWorkflow && <div className="trackb-mode-tabs">
                <button
                  className={missionMapView === "urban" ? "active" : ""}
                  onClick={() => void showMissionAnalysis(hackathonWorkflow, "urban")}
                >
                  Urban
                </button>
                <button
                  className={missionMapView === "rural" ? "active" : ""}
                  onClick={() => void showMissionAnalysis(hackathonWorkflow, "rural")}
                >
                  Rural
                </button>
              </div>}
              <span className="live-chip">context basemap · not evidence</span><span className="live-chip">deterministic</span>
            </div>
            <TrackBMap geojson={geojson} />
            {!geojson && <div className="map-empty"><strong>Awaiting spatial change geometry</strong><span>Run temporal intelligence or the full Track B mission to render measured change geometry.</span></div>}
          </div>

          <div className="metric-grid">
            {(result?.metrics ?? [
              { key: "change", label: "Changed pixels", value: "—", unit: "%" },
              { key: "area", label: "Changed area", value: "—", unit: "ha" },
              { key: "coverage", label: "Usable coverage", value: "—", unit: "%" },
            ]).slice(0, 4).map((m) => <article key={m.key} className="metric-card"><small>{m.label}</small><strong>{m.value}<em>{m.unit ?? ""}</em></strong></article>)}
          </div>

          <div className="trackb-bottom-grid">
            <section className="intel-card ai-copilot-card"><div className="panel-heading compact"><span>AI</span><div><strong>GeoPilot Planning Copilot</strong><small>measurement first · grounded planning intelligence</small></div></div>
              {!aiInsight ? <><p>{result?.summary ?? "Run temporal analysis first. GeoPilot AI then converts measured satellite change into planner-focused issues, relevance and next actions without inventing spatial values."}</p>{result && <button className="analysis-button ai-run-button" onClick={() => void runAIInterpretation()} disabled={aiBusy}>{aiBusy ? "AI reasoning…" : "Generate planning intelligence"}</button>}</> : <div className="ai-intelligence"><div className="ai-confidence"><span>Grounding</span><strong>{aiInsight.confidence}</strong><small>{aiInsight.provider} · {aiInsight.model}</small></div><h3>{aiInsight.planner_problem}</h3><p>{aiInsight.executive_summary}</p>{aiInsight.insights.map((item, i) => <article className="ai-insight" key={`${item.title}-${i}`}><strong>{item.title}</strong><p>{item.finding}</p><small>PLANNING RELEVANCE</small><p>{item.planning_relevance}</p><small>NEXT MOVE</small><p>{item.recommended_action}</p><div className="ai-evidence-tags">{item.evidence_refs.map((ref) => <code key={ref}>{ref}</code>)}</div></article>)}<div className="ai-next-actions"><strong>Planner action queue</strong>{aiInsight.next_actions.map((x) => <p key={x}>→ {x}</p>)}</div></div>}
              {result && <div className="intel-actions"><div className="method-chip">{result.method}</div>{result.report_url && <button className="report-button" onClick={() => void openEvidenceReport()} disabled={busy}>Evidence PDF</button>}</div>}</section>
            <section className="intel-card"><div className="panel-heading compact"><span>EV</span><div><strong>Evidence Lineage</strong><small>auditable evidence sources</small></div></div>{result ? result.evidence.map((e, i) => <div className="evidence-row" key={i}><span>{String(e.role ?? "source")}</span><code>{String(e.id).slice(0, 12)}…</code></div>) : <p>No analysis evidence yet.</p>}</section>
          </div>

          {result && <section className="planner-decision-workspace">
            <div className="decision-workspace-head">
              <div><span className="decision-kicker">AI DECISION WORKSPACE</span><h2>From change detection to planner action</h2><p>Ask a planning question or generate a decision brief. Every claim stays grounded in validated project, official-document, terrain, GIS, or temporal evidence.</p></div>
              <div className="decision-question"><label>Planner problem / question<textarea value={plannerQuestion} onChange={(e) => setPlannerQuestion(e.target.value)} placeholder="Example: Which measured change should I inspect first, and what should I verify before escalating it?" rows={3} /></label><button className="analysis-button" onClick={() => void runPlannerDecision()} disabled={aiBusy}>{aiBusy ? "GeoPilot reasoning…" : "Build decision brief"}</button></div>
            </div>
            {terrainPlanningRun ? (
              <div className="decision-grid">
                <article className="decision-priority priority-monitor">
                  <small>DETERMINISTIC TERRAIN EVIDENCE</small>
                  <strong>{terrainPlanningRun.status.toUpperCase()}</strong>
                  <span>terrain.site_summary</span>
                  <code>
                    {String(
                      terrainPlanningRun.provider_metadata?.provider ??
                        "evidence-bounded",
                    )} · {String(
                      terrainPlanningRun.provider_metadata?.model ??
                        "deterministic",
                    )}
                  </code>
                </article>

                <article className="decision-core">
                  <small>GEOPILOT TERRAIN ANSWER</small>
                  <h3>Terrain measurement result</h3>
                  <p>
                    {terrainPlanningRun.synthesis ??
                      "AI synthesis unavailable. Deterministic terrain evidence remains available."}
                  </p>
                </article>

                <article className="decision-evidence">
                  <small>EVIDENCE SUMMARY</small>
                  <p>
                    Terrain values are sourced from the validated
                    project/site DEM through terrain.site_summary.
                  </p>
                  <div className="ai-evidence-tags">
                    <code>TERRAIN_SITE_SUMMARY</code>
                    <code>DEM_EVIDENCE</code>
                  </div>
                  <details>
                    <summary>
                      Inspect deterministic evidence
                    </summary>
                    <pre>
                      {JSON.stringify(
                        terrainPlanningRun.evidence,
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </article>

                <article className="decision-limit">
                  <small>LIMITATIONS / REVIEW BOUNDARY</small>
                  {terrainPlanningRun.limitations.length ? (
                    terrainPlanningRun.limitations.map((item, i) => (
                      <p key={`${i}-${String(item).slice(0, 32)}`}>
                        • {String(item)}
                      </p>
                    ))
                  ) : (
                    <p>
                      • Terrain values are deterministic measurements
                      from the selected Site DEM.
                    </p>
                  )}
                  <p>
                    • Professional planning interpretation remains
                    separate from the measured terrain values.
                  </p>
                </article>
              </div>
            ) : !decision ? <div className="decision-empty"><strong>Decision brief not generated yet</strong><span>GeoPilot will convert the deterministic temporal result into Issue → Evidence → Priority → Planning implication → Action, without treating spectral change as statutory proof.</span></div> : <div className="decision-grid">
              <article className={`decision-priority priority-${decision.priority}`}><small>NON-STATUTORY TRIAGE</small><strong>{decision.priority.replace("_", " ")}</strong><span>{decision.confidence} confidence</span><code>{decision.provider} · {decision.model}</code></article>
              <article className="decision-core"><small>PLANNER ISSUE</small><h3>{decision.decision_title}</h3><GroundedMarkdown value={decision.issue} /><small>PLANNING IMPLICATION</small><GroundedMarkdown value={decision.planning_implication} /></article>
              <article className="decision-evidence"><small>EVIDENCE SUMMARY</small><GroundedMarkdown value={decision.evidence_summary} /><div className="ai-evidence-tags">{decision.evidence_refs.map((ref) => <code key={ref}>{ref}</code>)}</div></article>
              <div className="decision-actions"><div className="decision-section-title">Recommended planner actions</div>{decision.recommended_actions.map((item, i) => <article key={`${item.action}-${i}`}><span>{String(i + 1).padStart(2, "0")}</span><div><strong>{item.action}</strong><p>{item.rationale}</p><small>VERIFY → {item.verification_needed}</small><div className="ai-evidence-tags">{item.evidence_refs.map((ref) => <code key={ref}>{ref}</code>)}</div></div></article>)}</div>
              <article className="decision-limit"><small>LIMITATIONS / REVIEW BOUNDARY</small>{decision.limitations.map((item) => <p key={item}>• {item}</p>)}<p>• Professional review remains required; this priority is planner triage, not approval or compliance.</p></article>
            </div>}
          </section>}

          {result && <section className="limitations"><strong>Professional review boundary</strong>{result.limitations.map((x) => <p key={x}>• {x}</p>)}</section>}
          {error && <div className="trackb-error" role="alert">{error}</div>}
        </main>
      </div>

      <section className="planner-decision-workspace hackathon-simulation">
        <div className="decision-workspace-head">
          <div><span className="decision-kicker">HACKATHON SIMULATION MODE</span><h2>One-click Urban + Rural AI mission</h2><p>GeoPilot automatically selects eligible before/after evidence pairs for both contexts, runs deterministic temporal analysis, grounded AI interpretation, planner decision briefs, and strategic comparison.</p></div>
          <button className="analysis-button" onClick={() => void runHackathonSimulation()} disabled={hackathonBusy}>{hackathonBusy ? "Running full mission…" : "Run full Track B mission"}</button>
        </div>
        {hackathonWorkflow && <div className="decision-grid">
          <article className={`decision-priority priority-${hackathonWorkflow.status === "complete" ? "monitor" : "evidence_limited"}`}><small>MISSION STATUS</small><strong>{hackathonWorkflow.status}</strong><span>{hackathonWorkflow.stages.filter((x) => x.status === "pass").length}/{hackathonWorkflow.stages.length} stages passed</span><code>{hackathonWorkflow.workflow_id.slice(0, 12)}…</code></article>
          <article className="decision-core"><small>URBAN RESULT</small><h3>{hackathonWorkflow.urban_analysis.changed_percentage.toFixed(2)}% measured change</h3><p>{hackathonWorkflow.urban_decision?.planning_implication ?? hackathonWorkflow.urban_analysis.summary}</p><small>RURAL RESULT</small><p>{hackathonWorkflow.rural_analysis.changed_percentage.toFixed(2)}% measured change · {hackathonWorkflow.rural_decision?.planning_implication ?? hackathonWorkflow.rural_analysis.summary}</p></article>
          <article className="decision-evidence"><small>STRATEGIC AI COMPARISON</small><p>{hackathonWorkflow.comparison?.strategic_summary ?? "AI comparison unavailable; deterministic evidence remains valid."}</p><div className="ai-evidence-tags"><code>PROVENANCE_CONTROLLED</code><code>URBAN_T1_T2</code><code>RURAL_T1_T2</code></div></article>
          <div className="decision-actions"><div className="decision-section-title">Mission execution trace</div>{hackathonWorkflow.stages.map((stage, i) => <article key={stage.key}><span>{String(i + 1).padStart(2, "0")}</span><div><strong>{stage.label} · {stage.status.toUpperCase()}</strong><p>{stage.detail}</p></div></article>)}</div>
        </div>}
      </section>

      <section className="trackb-dataset-table">
        <div className="panel-heading"><span>DB</span><div><strong>Organizer Dataset Registry</strong><small>immutable checksum + temporal provenance</small></div></div>
        <div className="dataset-table-head"><span>Dataset</span><span>Scope</span><span>Bands</span><span>Grid</span><span>Evidence</span></div>
        {datasets.map((d) => <div className="dataset-table-row" key={d.id}><span><strong>{d.name}</strong><small>{d.acquisition_datetime ?? "date not supplied"}</small></span><span>{label(d.provenance.location_type)} · {label(d.provenance.temporal_role)}</span><span>{d.band_names.join(", ")}</span><span>{d.width}×{d.height}<small>{d.crs}</small></span><span className="verified">✓ organizer</span></div>)}
        {!datasets.length && <p className="dataset-empty">No organizer raster registered yet.</p>}
      </section>
    </section>
  );
}











