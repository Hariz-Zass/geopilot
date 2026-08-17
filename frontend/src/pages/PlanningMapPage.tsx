import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { PlanningMap } from "../features/map/PlanningMap";
import { ApiError } from "../lib/api/errors";
import { sitesApi, type SiteResponse } from "../lib/api/sites";
import { getSessionAccessToken } from "../lib/auth/session";

type State =
  | { status: "loading" }
  | { status: "unauthenticated" }
  | { status: "empty" }
  | { status: "error"; message: string; requestId?: string }
  | { status: "ready"; site: SiteResponse };

export function PlanningMapPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    if (!projectId) {
      setState({ status: "error", message: "Project context is missing." });
      return;
    }
    const token = getSessionAccessToken();
    if (!token) {
      setState({ status: "unauthenticated" });
      return;
    }
    let active = true;
    sitesApi.active(projectId, token)
      .then((site) => {
        if (active) setState({ status: "ready", site });
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 404 && error.code === "site_not_found") {
          setState({ status: "empty" });
          return;
        }
        if (error instanceof ApiError) {
          setState({ status: "error", message: error.message, requestId: error.requestId });
          return;
        }
        setState({ status: "error", message: "Unable to load the active Site." });
      });
    return () => { active = false; };
  }, [projectId]);

  if (state.status === "loading") return <section className="panel"><p role="status">Loading active Site…</p></section>;
  if (state.status === "unauthenticated") return (
    <section className="panel"><p className="eyebrow">Map context</p><h1>Authentication required</h1><p>The planning map only loads project-owned Site geometry after an authenticated session is available.</p></section>
  );
  if (state.status === "empty") return (
    <section className="panel"><p className="eyebrow">Map context</p><h1>No active Site</h1><p>This Project has no active, non-archived Site to display.</p><Link to="/">Return home</Link></section>
  );
  if (state.status === "error") return (
    <section className="panel"><p className="eyebrow">Map context</p><h1>Unable to load map context</h1><div className="status-card status-error" role="alert"><p>{state.message}</p>{state.requestId && <small>Request ID: {state.requestId}</small>}</div></section>
  );
  return <PlanningMap site={state.site} />;
}
