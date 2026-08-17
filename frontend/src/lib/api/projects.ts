import { apiClient } from "./client";

export type ProjectResponse = {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
};

function bearer(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` };
}

export const projectsApi = {
  list: (accessToken: string) =>
    apiClient.get<ProjectResponse[]>("/api/v1/projects", {
      headers: bearer(accessToken),
    }),

  get: (projectId: string, accessToken: string) =>
    apiClient.get<ProjectResponse>(`/api/v1/projects/${encodeURIComponent(projectId)}`, {
      headers: bearer(accessToken),
    }),

  create: (
    payload: { name: string; description?: string | null },
    accessToken: string,
  ) =>
    apiClient.request<ProjectResponse>("/api/v1/projects", {
      method: "POST",
      headers: {
        ...bearer(accessToken),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
};