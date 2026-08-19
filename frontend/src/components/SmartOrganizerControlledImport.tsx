import { useMemo, useState } from "react";

import { ApiError } from "../lib/api/errors";
import {
  trackBApi,
  type TrackBOrganizerImportAllResponse,
  type TrackBOrganizerImportPlan,
  type TrackBOrganizerIntakeReport,
  type TrackBGisTemporalReport,
  type TrackBGisTemporalResult,
  type TrackBOrganizerSiteCandidate,
  type TrackBOrganizerSiteDiscovery,
  type TrackBOrganizerSiteResolution,
} from "../lib/api/trackB";

type Props = {
  projectId: string;
  token: string;
  onCommitted?: () => void | Promise<void>;
  onTemporalResult?: (result: TrackBGisTemporalResult | undefined) => void;
};

const ROLE_OPTIONS = [
  ["", "Select role"],
  ["land_use", "Land use"],
  ["zoning", "Zoning"],
  ["planning_block", "Planning block"],
  ["planning_subzone", "Planning subzone"],
  ["transport_network", "Transport network"],
  ["parcel", "Parcel / cadastral"],
  ["reference", "Reference GIS"],
] as const;

const TEMPORAL_QUESTIONS = [
  "What are the biggest verified land-use transitions?",
  "How much verified area was reclassified?",
  "What did Tanah Kosong change into?",
  "How much Hutan changed to Pertanian?",
  "Apakah perubahan guna tanah utama antara 2023 dan 2024?",
] as const;

function errorMessage(error: unknown) {
  return error instanceof ApiError
    ? error.message
    : error instanceof Error
      ? error.message
      : "Smart Organizer request failed.";
}

function candidateLabel(candidate: TrackBOrganizerSiteCandidate) {
  return `${candidate.logical_name} · ${candidate.candidate_status.replaceAll("_", " ")}`;
}

export function SmartOrganizerControlledImport({ projectId, token, onCommitted, onTemporalResult }: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const [intake, setIntake] = useState<TrackBOrganizerIntakeReport>();
  const [temporal, setTemporal] = useState<TrackBGisTemporalReport>();
  const [temporalResult, setTemporalResult] = useState<TrackBGisTemporalResult>();
  const [planningAnswer, setPlanningAnswer] = useState<{ synthesis: string | null; limitations: string[]; status: string }>();
  const [temporalQuestion, setTemporalQuestion] = useState<string>(TEMPORAL_QUESTIONS[0]);
  const [temporalBusy, setTemporalBusy] = useState<"analysis" | "ai">();
  const [temporalError, setTemporalError] = useState<string>();
  const [discovery, setDiscovery] = useState<TrackBOrganizerSiteDiscovery>();
  const [selectedCandidate, setSelectedCandidate] = useState("");
  const [siteGeometry, setSiteGeometry] = useState<Record<string, unknown>>();
  const [siteName, setSiteName] = useState("Competition Site");
  const [siteSourceRef, setSiteSourceRef] = useState("organizer_package");
  const [plan, setPlan] = useState<TrackBOrganizerImportPlan>();
  const [roles, setRoles] = useState<Record<string, string>>({});
  const [dryRun, setDryRun] = useState<TrackBOrganizerImportAllResponse>();
  const [commitResult, setCommitResult] = useState<TrackBOrganizerImportAllResponse>();
  const [busy, setBusy] = useState<string>();
  const [error, setError] = useState<string>();
  const [finalConfirmed, setFinalConfirmed] = useState(false);

  const usableCandidates = useMemo(
    () => (discovery?.candidates ?? []).filter((item) => Boolean(item.union_geometry)),
    [discovery],
  );

  const importCandidates = useMemo(
    () => (plan?.datasets ?? []).filter((item) => item.decision === "IMPORT_CANDIDATE"),
    [plan],
  );

  const rolesComplete =
    importCandidates.length > 0 &&
    importCandidates.every((item) => Boolean(roles[item.logical_name]));

  function resetAfterFiles(next: File[]) {
    setFiles(next);
    setIntake(undefined);
    setTemporal(undefined);
    setTemporalResult(undefined);
    setPlanningAnswer(undefined);
    setTemporalQuestion(TEMPORAL_QUESTIONS[0]);
    setTemporalError(undefined);
    setDiscovery(undefined);
    setSelectedCandidate("");
    setSiteGeometry(undefined);
    setPlan(undefined);
    setRoles({});
    setDryRun(undefined);
    setCommitResult(undefined);
    setFinalConfirmed(false);
    setError(undefined);
    onTemporalResult?.(undefined);
  }

  async function analyze() {
    if (!files.length) {
      setError("Choose one or more organizer files or a ZIP package first.");
      return;
    }
    setBusy("analyze");
    setError(undefined);
    setPlan(undefined);
    setDryRun(undefined);
    setCommitResult(undefined);
    try {
      const [nextIntake, nextDiscovery, nextTemporal] = await Promise.all([
        trackBApi.inspectOrganizerPackage(projectId, files, token),
        trackBApi.discoverOrganizerSiteCandidates(projectId, files, token),
        trackBApi.inspectGisTemporal(projectId, files, token),
      ]);
      setIntake(nextIntake);
      setDiscovery(nextDiscovery);
      setTemporal(nextTemporal);

      const recommendedName = nextDiscovery.recommendation.logical_name;
      const suggested = recommendedName
        ? nextDiscovery.candidates.find(
            (item) => item.logical_name === recommendedName && Boolean(item.union_geometry),
          )
        : undefined;

      if (suggested?.union_geometry) {
        setSelectedCandidate(suggested.logical_name);
        setSiteGeometry(suggested.union_geometry);
        setSiteSourceRef(`organizer_candidate:${suggested.logical_name}`);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(undefined);
    }
  }

  async function runTemporalAnalysis() {
    if (!files.length || temporal?.pair.pair_status !== "PAIR_COMPATIBLE") {
      setTemporalError("Choose a compatible GIS temporal pair before running the analysis.");
      return;
    }
    setTemporalBusy("analysis");
    setTemporalError(undefined);
    setTemporalResult(undefined);
    setPlanningAnswer(undefined);
    try {
      const nextResult = await trackBApi.analyzeGisTemporalExact(projectId, files, token);
      setTemporalResult(nextResult);
      onTemporalResult?.(nextResult);
    } catch (caught) {
      setTemporalError(caught instanceof ApiError ? caught.message : "GIS temporal analysis failed. Please retry.");
    } finally {
      setTemporalBusy(undefined);
    }
  }

  async function askGeoPilot() {
    if (!temporalResult) return;
    setTemporalBusy("ai");
    setTemporalError(undefined);
    try {
      setPlanningAnswer(await trackBApi.askGisTemporal(
        projectId,
        temporalQuestion,
        temporalResult as unknown as Record<string, unknown>,
        token,
      ));
    } catch (caught) {
      setTemporalError(caught instanceof ApiError ? caught.message : "GeoPilot could not prepare a grounded answer. Please retry.");
    } finally {
      setTemporalBusy(undefined);
    }
  }

  function chooseCandidate(logicalName: string) {
    setSelectedCandidate(logicalName);
    const candidate = usableCandidates.find((item) => item.logical_name === logicalName);
    setSiteGeometry(candidate?.union_geometry ?? undefined);
    setSiteSourceRef(
      candidate ? `organizer_candidate:${candidate.logical_name}` : "organizer_package",
    );
    setPlan(undefined);
    setDryRun(undefined);
    setCommitResult(undefined);
    setFinalConfirmed(false);
  }

  async function uploadBoundary(boundary: File) {
    setBusy("boundary");
    setError(undefined);
    try {
      const next: TrackBOrganizerSiteResolution = await trackBApi.uploadOrganizerSiteBoundary(
        projectId,
        siteName,
        boundary,
        true,
        token,
      );
      if (!next.ready_for_site_creation || !next.geometry) {
        throw new Error("Uploaded boundary was not validated as a competition Site.");
      }
      setSiteGeometry(next.geometry);
      setSelectedCandidate("");
      setSiteSourceRef(boundary.name);
      setPlan(undefined);
      setRoles({});
      setDryRun(undefined);
      setCommitResult(undefined);
      setFinalConfirmed(false);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(undefined);
    }
  }

  async function buildPlan() {
    if (!siteGeometry) {
      setError("Confirm an organizer Site candidate or upload a valid GeoJSON boundary first.");
      return;
    }
    setBusy("plan");
    setError(undefined);
    try {
      const next = await trackBApi.planOrganizerImport(
        projectId,
        { siteName, siteGeometry, siteSourceRef, files, userConfirmed: true },
        token,
      );
      setPlan(next);
      const kept: Record<string, string> = {};
      for (const item of next.datasets) {
        const existingRole = roles[item.logical_name];
        if (item.decision === "IMPORT_CANDIDATE" && existingRole) {
          kept[item.logical_name] = existingRole;
        }
      }
      setRoles(kept);
      setDryRun(undefined);
      setCommitResult(undefined);
      setFinalConfirmed(false);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(undefined);
    }
  }

  async function runImport(executePersistent: boolean) {
    if (!siteGeometry || !rolesComplete) {
      setError("Site confirmation and an explicit role for every import candidate are required.");
      return;
    }
    if (executePersistent && !finalConfirmed) {
      setError("Tick the final confirmation before persistent Import All.");
      return;
    }

    setBusy(executePersistent ? "commit" : "dryrun");
    setError(undefined);
    try {
      const result = await trackBApi.importOrganizerPackage(
        projectId,
        {
          siteName,
          siteGeometry,
          siteSourceRef,
          roleAssignments: roles,
          files,
          userConfirmed: true,
          allowInvalidGeometrySkip: false,
          executePersistent,
        },
        token,
      );

      if (executePersistent) {
        setCommitResult(result);
        if (result.committed) await onCommitted?.();
      } else {
        setDryRun(result);
      }
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(undefined);
    }
  }

  return (
    <section className="smart-organizer-flow">
      <div className="smart-organizer-flow-head">
        <div>
          <span>SMART ORGANIZER · CONTROLLED IMPORT</span>
          <strong>Organizer package → Site → spatial scope → Import All</strong>
          <small>Persistent database write is impossible until Site and dataset roles are explicitly confirmed.</small>
        </div>
        <code>PHASE 2D.1</code>
      </div>

      <div className="smart-organizer-step">
        <div className="smart-organizer-step-title"><b>1</b><span>Organizer package</span></div>
        <input
          type="file"
          multiple
          accept=".zip,.gpkg,.tab,.dat,.map,.id,.ind,.shp,.shx,.dbf,.prj,.cpg,.qix,.geojson,.json,.pdf,.csv,.tif,.tiff,.jp2"
          onChange={(event) => resetAfterFiles(Array.from(event.currentTarget.files ?? []).filter((file) => file.size > 0))}
        />
        <div className="smart-organizer-actions">
          <button className="neon-button" type="button" disabled={!files.length || Boolean(busy)} onClick={() => void analyze()}>
            {busy === "analyze" ? "Analyzing…" : "Analyze organizer package"}
          </button>
          <small>{files.length ? `${files.length} file(s) selected` : "ZIP or multiple organizer files supported"}</small>
        </div>
        {intake && (
          <div className="smart-organizer-mini-grid">
            <span><strong>{intake.file_count}</strong>files</span>
            <span><strong>{intake.supported_or_reviewable_count}</strong>recognized</span>
            <span><strong>{intake.requires_confirmation_count}</strong>confirm</span>
            <span><strong>{intake.blocker_count}</strong>blockers</span>
          </div>
        )}
      </div>

      {discovery && (
        <div className="smart-organizer-step">
          <div className="smart-organizer-step-title"><b>2</b><span>Competition Site</span></div>
          <p className="smart-organizer-note">
            Discovery: <strong>{discovery.recommendation.status.replaceAll("_", " ")}</strong>. GeoPilot will never turn a large parcel layer into a Site automatically.
          </p>

          {usableCandidates.length > 0 && (
            <label>
              Organizer Site candidate
              <select value={selectedCandidate} onChange={(event) => chooseCandidate(event.target.value)}>
                <option value="">Choose boundary candidate</option>
                {usableCandidates.map((candidate) => (
                  <option key={`${candidate.logical_name}-${candidate.candidate_status}`} value={candidate.logical_name}>
                    {candidateLabel(candidate)}
                  </option>
                ))}
              </select>
            </label>
          )}

          <div className="smart-organizer-two">
            <label>
              Site name
              <input value={siteName} onChange={(event) => setSiteName(event.target.value)} />
            </label>
            <label>
              Fallback boundary
              <input
                type="file"
                accept=".geojson,.json"
                onChange={(event) => {
                  const boundary = event.currentTarget.files?.[0];
                  if (boundary) void uploadBoundary(boundary);
                }}
              />
            </label>
          </div>

          <div className="smart-organizer-actions">
            <button className="analysis-button" type="button" disabled={!siteGeometry || Boolean(busy)} onClick={() => void buildPlan()}>
              {busy === "plan" ? "Scoping…" : "Confirm Site & build spatial import plan"}
            </button>
            <small>{siteGeometry ? `Boundary ready · ${siteSourceRef}` : "No usable boundary yet — choose candidate or upload organizer GeoJSON"}</small>
          </div>
        </div>
      )}

      {plan && (
        <div className="smart-organizer-step">
          <div className="smart-organizer-step-title"><b>3</b><span>Spatial import plan</span></div>
          <div className="smart-organizer-mini-grid">
            <span><strong>{plan.totals.import_candidate_datasets}</strong>import</span>
            <span><strong>{plan.totals.skip_no_overlap_datasets}</strong>no overlap</span>
            <span><strong>{plan.totals.skip_empty_datasets}</strong>empty</span>
            <span><strong>{plan.totals.review_datasets}</strong>review</span>
          </div>

          <div className="smart-organizer-datasets">
            {plan.datasets.map((item) => (
              <article key={item.logical_name} className={item.decision === "IMPORT_CANDIDATE" ? "import" : "skip"}>
                <div>
                  <strong>{item.logical_name}</strong>
                  <small>{item.decision.replaceAll("_", " ")} · {item.intersecting_feature_count}/{item.source_feature_count} intersect</small>
                </div>
                {item.decision === "IMPORT_CANDIDATE" ? (
                  <select
                    value={roles[item.logical_name] ?? ""}
                    onChange={(event) => setRoles((current) => ({ ...current, [item.logical_name]: event.target.value }))}
                  >
                    {ROLE_OPTIONS.map(([value, text]) => <option key={value || "empty"} value={value}>{text}</option>)}
                  </select>
                ) : (
                  <code>{item.decision}</code>
                )}
              </article>
            ))}
          </div>

          {!importCandidates.length && <p className="smart-organizer-block">Import All blocked: no organizer GIS dataset intersects the confirmed Site.</p>}

          {importCandidates.length > 0 && (
            <div className="smart-organizer-actions">
              <button className="neon-button" type="button" disabled={!rolesComplete || Boolean(busy)} onClick={() => void runImport(false)}>
                {busy === "dryrun" ? "Checking…" : "Review final Import All"}
              </button>
              <small>{rolesComplete ? "All import candidates have explicit roles." : "Assign a role to every import candidate."}</small>
            </div>
          )}
        </div>
      )}

      {dryRun && (
        <div className="smart-organizer-step smart-organizer-final">
          <div className="smart-organizer-step-title"><b>4</b><span>Final confirmation</span></div>
          <p>Dry-run status: <strong>{dryRun.status.replaceAll("_", " ")}</strong>. No database write has occurred.</p>
          <label className="smart-organizer-confirm">
            <input type="checkbox" checked={finalConfirmed} onChange={(event) => setFinalConfirmed(event.target.checked)} />
            I confirm this Site and dataset-role mapping are derived from the organizer materials and authorize persistent Import All.
          </label>
          <button className="analysis-button" type="button" disabled={!finalConfirmed || Boolean(busy) || dryRun.status !== "ready_for_commit"} onClick={() => void runImport(true)}>
            {busy === "commit" ? "Importing…" : "CONFIRM & IMPORT ALL"}
          </button>
        </div>
      )}

      {temporal && (
        <div className="smart-organizer-step smart-organizer-temporal-evidence">
          <div className="smart-organizer-step-title"><b>GIS</b><span>GIS TEMPORAL EVIDENCE</span></div>
          <p>Metadata-only inspection. Geometry was not materialized and no database write occurred.</p>
          <div className="smart-organizer-dataset-grid">
            {temporal.datasets.filter((item) => item.semantic_domain === "LAND_USE").map((item) => (
              <article key={item.logical_name} className="smart-organizer-dataset">
                <strong>{item.logical_name}</strong>
                <span>{item.semantic_role.replaceAll("_", " ")} · {item.classification_confidence}</span>
                <small>{item.year_candidates.join(" / ") || "Year review required"} · {item.feature_count ?? "count unavailable"} features</small>
              </article>
            ))}
          </div>
          <strong>Pair status: {temporal.pair.pair_status.replaceAll("_", " ")}</strong>
          {temporal.pair.warnings.map((warning) => <small key={warning}>{warning}</small>)}
          {temporal.pair.block_reasons.map((reason) => <small key={reason} className="smart-organizer-error-text">{reason}</small>)}
          <div className="smart-organizer-actions">
            <button
              className="analysis-button"
              type="button"
              disabled={temporal.pair.pair_status !== "PAIR_COMPATIBLE" || !files.length || Boolean(busy) || Boolean(temporalBusy)}
              onClick={() => void runTemporalAnalysis()}
            >
              {temporalBusy === "analysis" ? "Analyzing 2023 → 2024 land-use change…" : "Run GIS Temporal Analysis"}
            </button>
            <small>Exact-geometry GIS analysis is explicit and does not run during inspection.</small>
          </div>
          {temporalError && <div className="smart-organizer-error"><strong>GIS temporal analysis blocked</strong><span>{temporalError}</span></div>}
        </div>
      )}

      {temporalResult && !onTemporalResult && (
        <div className="smart-organizer-step smart-organizer-temporal-result" aria-live="polite">
          <div className="smart-organizer-step-title"><b>GIS</b><span>GIS TEMPORAL CHANGE INTELLIGENCE</span></div>
          <div className="smart-organizer-temporal-pair">
            <span><small>BEFORE</small><strong>{temporalResult.dataset_pair.before_dataset} · {temporalResult.dataset_pair.before_year}</strong></span>
            <span><small>AFTER</small><strong>{temporalResult.dataset_pair.after_dataset} · {temporalResult.dataset_pair.after_year}</strong></span>
          </div>
          <div className="smart-organizer-mini-grid">
            <span><strong>{temporalResult.exact_match_count}</strong>exact geometry matches</span>
            <span><strong>{temporalResult.verified_reclassified_count}</strong>verified reclassified polygons</span>
            <span><strong>{temporalResult.verified_changed_area_ha.toFixed(3)}</strong>verified reclassified area among exact-geometry matches (ha)</span>
            <span><strong>{temporalResult.unchanged_count}</strong>unchanged exact matches</span>
            <span><strong>{temporalResult.unmatched_counts.before}</strong>unmatched before</span>
            <span><strong>{temporalResult.unmatched_counts.after}</strong>unmatched after</span>
            <span><strong>{temporalResult.runtime.total_runtime_seconds.toFixed(2)}s</strong>runtime</span>
            <span><strong>{temporalResult.matching_method}</strong>{temporalResult.confidence} · deterministic</span>
          </div>
          <h4>Top Verified Transitions</h4>
          {temporalResult.top_gtn1_transitions.length ? temporalResult.top_gtn1_transitions.map((transition, index) => (
            <div className="smart-organizer-transition" key={`${transition.before_category}-${transition.after_category}-${index}`}>
              <strong>{transition.before_category || "Unclassified"} → {transition.after_category || "Unclassified"}</strong>
              <span>{transition.feature_count} polygons · {transition.measured_area_ha.toFixed(3)} ha</span>
            </div>
          )) : <small>No bounded GTN1 transitions were returned.</small>}
          <div className="smart-organizer-limitation-card">
            <strong>Exact-geometry analysis only.</strong>
            <span>{temporalResult.unmatched_label}</span>
            {temporalResult.limitations.map((limitation) => <small key={limitation}>{limitation}</small>)}
          </div>
          <details className="smart-organizer-provenance">
            <summary>Provenance and audit metadata</summary>
            <span>Analysis ID: {temporalResult.analysis_id}</span>
            <span>Before checksum: {temporalResult.checksums.before.slice(0, 12)}…</span>
            <span>After checksum: {temporalResult.checksums.after.slice(0, 12)}…</span>
            <span>Method: {temporalResult.matching_method} · deterministic: {String(temporalResult.deterministic)}</span>
          </details>
          <label className="smart-organizer-question">
            Suggested question
            <select value={temporalQuestion} onChange={(event) => setTemporalQuestion(event.target.value)} disabled={temporalBusy === "ai"}>
              {TEMPORAL_QUESTIONS.map((question) => <option key={question} value={question}>{question}</option>)}
            </select>
          </label>
          <button className="neon-button" type="button" disabled={temporalBusy === "ai"} onClick={() => void askGeoPilot()}>
            {temporalBusy === "ai" ? "Preparing GeoPilot…" : "Ask GeoPilot about this result"}
          </button>
          {planningAnswer && <div className="smart-organizer-ai-result"><strong>GeoPilot response · {planningAnswer.status}</strong><span>{planningAnswer.synthesis || "Validated evidence was handed off, but no synthesis was produced."}</span>{planningAnswer.limitations.map((limitation) => <small key={limitation}>{limitation}</small>)}</div>}
        </div>
      )}

      {temporalResult && onTemporalResult && (
        <div className="smart-organizer-step smart-organizer-temporal-result-compact" aria-live="polite">
          <div className="smart-organizer-step-title"><b>GIS</b><span>GIS RESULT READY</span></div>
          <strong>{temporalResult.dataset_pair.before_year} → {temporalResult.dataset_pair.after_year} · {temporalResult.confidence}</strong>
          <small>Detailed GIS Temporal Change Intelligence is displayed in the main workspace.</small>
        </div>
      )}

      {commitResult?.committed && (
        <div className="smart-organizer-success">
          <strong>Import All committed successfully.</strong>
          <span>Site {commitResult.site_created ? "created" : "reused"} · {commitResult.layers_created} layer(s) created · {commitResult.features_created} feature(s) created · {commitResult.features_duplicates_skipped ?? 0} duplicate feature(s) skipped.</span>
        </div>
      )}

      {error && <div className="smart-organizer-error"><strong>Smart Organizer blocked</strong><span>{error}</span></div>}
    </section>
  );
}
