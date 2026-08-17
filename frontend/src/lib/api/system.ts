import { apiClient } from "./client";

export type HealthResponse = {
  status: string;
  service?: string;
  version?: string;
};

export type ReadinessResponse = {
  status: string;
  database?: unknown;
};

export const systemApi = {
  health: () => apiClient.get<HealthResponse>("/api/v1/system/health"),
  ready: () => apiClient.get<ReadinessResponse>("/api/v1/system/ready"),
};
