import { useMemo, useState } from "react";

import { ApiError } from "../lib/api/errors";
import {
  trackBApi,
  type TrackBOrganizerImportAllResponse,
  type TrackBOrganizerImportPlan,
  type TrackBOrganizerIntakeReport,
  type TrackBOrganizerSiteCandidate,
  type TrackBOrganizerSiteDiscovery,
  type TrackBOrganizerSiteResolution,
} from "../lib/api/trackB";

type Props = {
  projectId: string;
  token: string;
  onCommitted?: () => void | Promise<void>;
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

export function SmartOrganizerControlledImport({ projectId, token, onCommitted }: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const [intake, setIntake] = useState<TrackBOrganizerIntakeReport>();
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
    setDiscovery(undefined);
    setSelectedCandidate("");
    setSiteGeometry(undefined);
    setPlan(undefined);
    setRoles({});
    setDryRun(undefined);
    setCommitResult(undefined);
    setFinalConfirmed(false);
    setError(undefined);
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
      const [nextIntake, nextDiscovery] = await Promise.all([
        trackBApi.inspectOrganizerPackage(projectId, files, token),
        trackBApi.discoverOrganizerSiteCandidates(projectId, files, token),
      ]);
      setIntake(nextIntake);
      setDiscovery(nextDiscovery);

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
