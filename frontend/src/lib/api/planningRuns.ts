import { apiClient } from "./client";

export type PlanningRunResponse = {
  id: string;
  project_id: string;
  site_id: string;
  created_by_user_id: string;

  question: string;
  development_intent: string | null;

  status: string;

  plan: unknown[];
  evidence: unknown[];
  findings: unknown[];
  limitations: unknown[];

  provider_metadata: Record<string, unknown>;

  synthesis: string | null;

  review_state: string;

  created_at: string;
  updated_at: string;
};

function bearer(
  token: string,
): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
  };
}

export const planningRunsApi = {
  create: (
    projectId: string,
    siteId: string,
    payload: {
      question: string;
      development_intent?: string | null;
      temporal_evidence?: Record<string, unknown> | null;
    },
    accessToken: string,
  ) =>
    apiClient.request<PlanningRunResponse>(
      `/api/v1/projects/${encodeURIComponent(
        projectId,
      )}/sites/${encodeURIComponent(
        siteId,
      )}/planning-runs`,
      {
        method: "POST",
        headers: {
          ...bearer(accessToken),
          "Content-Type":
            "application/json",
        },
        body: JSON.stringify(payload),
      },
    ),

  get: (
    projectId: string,
    siteId: string,
    runId: string,
    accessToken: string,
  ) =>
    apiClient.get<PlanningRunResponse>(
      `/api/v1/projects/${encodeURIComponent(
        projectId,
      )}/sites/${encodeURIComponent(
        siteId,
      )}/planning-runs/${encodeURIComponent(
        runId,
      )}`,
      {
        headers: bearer(accessToken),
      },
    ),

  execute: (
    projectId: string,
    siteId: string,
    runId: string,
    accessToken: string,
  ) =>
    apiClient.request<PlanningRunResponse>(
      `/api/v1/projects/${encodeURIComponent(
        projectId,
      )}/sites/${encodeURIComponent(
        siteId,
      )}/planning-runs/${encodeURIComponent(
        runId,
      )}/execute`,
      {
        method: "POST",
        headers: bearer(accessToken),
      },
    ),
};