import { useEffect, useState } from "react";
import { ApiError } from "../lib/api/errors";
import { systemApi, type ReadinessResponse } from "../lib/api/system";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; data: ReadinessResponse }
  | { status: "error"; message: string; requestId?: string };

export function SystemPage() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let active = true;
    systemApi
      .ready()
      .then((data) => {
        if (active) setState({ status: "ready", data });
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError) {
          setState({ status: "error", message: error.message, requestId: error.requestId });
          return;
        }
        setState({ status: "error", message: "Unable to reach the GeoPilot API." });
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <section className="panel">
      <p className="eyebrow">Runtime status</p>
      <h1>System readiness</h1>
      {state.status === "loading" && <p role="status">Checking backend readiness…</p>}
      {state.status === "ready" && (
        <div className="status-card status-ready">
          <strong>Ready</strong>
          <p>Backend database readiness returned: {state.data.status}</p>
        </div>
      )}
      {state.status === "error" && (
        <div className="status-card status-error" role="alert">
          <strong>Not ready</strong>
          <p>{state.message}</p>
          {state.requestId && <small>Request ID: {state.requestId}</small>}
        </div>
      )}
    </section>
  );
}
