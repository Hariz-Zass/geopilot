import { apiClient } from "./client";

export type MultiPolygonGeometry = {
  type: "MultiPolygon";
  coordinates: number[][][][];
};

export type SiteResponse = {
  id: string;
  project_id: string;
  name: string;
  geometry: MultiPolygonGeometry;
  geometry_hash: string;
  geometry_revision: number;
  is_active: boolean;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
};

function bearer(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export const sitesApi = {
  active: (projectId: string, accessToken: string) =>
    apiClient.get<SiteResponse>(`/api/v1/projects/${encodeURIComponent(projectId)}/sites/active`, {
      headers: bearer(accessToken),
    }),

  list: (projectId: string, accessToken: string) =>
    apiClient.get<SiteResponse[]>(`/api/v1/projects/${encodeURIComponent(projectId)}/sites`, {
      headers: bearer(accessToken),
    }),

  create: (
    projectId: string,
    payload: { name: string; geometry: unknown; is_active: boolean },
    accessToken: string,
  ) =>
    apiClient.request<SiteResponse>(`/api/v1/projects/${encodeURIComponent(projectId)}/sites`, {
      method: "POST",
      headers: {
        ...bearer(accessToken),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
};