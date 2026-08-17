export type FrontendEnv = Readonly<{
  apiBaseUrl: string;
  appName: string;
  mapStyleUrl: string;
}>;

function normalizeBaseUrl(value: string): string {
  return value.replace(/\/+$/, "");
}

export function readFrontendEnv(source: ImportMetaEnv = import.meta.env): FrontendEnv {
  const rawApiBaseUrl = source.VITE_API_BASE_URL?.trim();
  if (!rawApiBaseUrl) {
    throw new Error("VITE_API_BASE_URL is required");
  }

  let parsed: URL;
  try {
    parsed = new URL(rawApiBaseUrl);
  } catch {
    throw new Error("VITE_API_BASE_URL must be an absolute URL");
  }

  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error("VITE_API_BASE_URL must use http or https");
  }

  return Object.freeze({
    apiBaseUrl: normalizeBaseUrl(rawApiBaseUrl),
    appName: source.VITE_APP_NAME?.trim() || "GeoPilot AI",
    mapStyleUrl: source.VITE_MAP_STYLE_URL?.trim() || "https://demotiles.maplibre.org/style.json",
  });
}

export const frontendEnv = readFrontendEnv();
