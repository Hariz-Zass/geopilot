import { describe, expect, it } from "vitest";
import { readFrontendEnv } from "./env";

function env(values: Record<string, string | undefined>): ImportMetaEnv {
  return values as ImportMetaEnv;
}

describe("readFrontendEnv", () => {
  it("normalizes the API base URL", () => {
    const value = readFrontendEnv(env({ VITE_API_BASE_URL: "http://localhost:8000/" }));
    expect(value.apiBaseUrl).toBe("http://localhost:8000");
    expect(value.appName).toBe("GeoPilot AI");
  });

  it("fails closed when API URL is missing", () => {
    expect(() => readFrontendEnv(env({}))).toThrow("VITE_API_BASE_URL is required");
  });

  it("rejects unsupported protocols", () => {
    expect(() => readFrontendEnv(env({ VITE_API_BASE_URL: "file:///tmp/api" }))).toThrow(
      "must use http or https",
    );
  });
});
