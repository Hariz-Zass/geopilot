import { frontendEnv } from "../../config/env";
import { ApiError, type ApiErrorPayload } from "./errors";

export type ApiClientOptions = {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
};

export class ApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;

  constructor(options: ApiClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? frontendEnv.apiBaseUrl).replace(/\/+$/, "");
    this.fetchImpl =
  options.fetchImpl ??
  ((input: RequestInfo | URL, init?: RequestInit) =>
    globalThis.fetch(input, init));
  }

  async get<T>(path: string, init?: RequestInit): Promise<T> {
    return this.request<T>(path, { ...init, method: "GET" });
  }

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...init.headers,
      },
    });

    const requestId = response.headers.get("x-request-id") ?? undefined;
    const contentType = response.headers.get("content-type") ?? "";
    const body = contentType.includes("application/json")
      ? ((await response.json()) as unknown)
      : undefined;

    if (!response.ok) {
      const payload = (body ?? {}) as ApiErrorPayload;
      throw new ApiError({
        status: response.status,
        code: payload.error?.code,
        message: payload.error?.message ?? `Request failed with HTTP ${response.status}`,
        requestId: payload.error?.request_id ?? requestId,
      });
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return body as T;
  }
}

export const apiClient = new ApiClient();
