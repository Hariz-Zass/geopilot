import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "./client";
import { ApiError } from "./errors";

describe("ApiClient", () => {
  it("returns typed JSON for a successful request", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json", "x-request-id": "req-1" },
      }),
    );
    const client = new ApiClient({ baseUrl: "http://example.test", fetchImpl });
    await expect(client.get<{ status: string }>("/health")).resolves.toEqual({ status: "ok" });
    expect(fetchImpl).toHaveBeenCalledWith(
      "http://example.test/health",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("maps backend error contracts into ApiError", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(
        JSON.stringify({ error: { code: "database_not_ready", message: "Database unavailable", request_id: "req-2" } }),
        { status: 503, headers: { "content-type": "application/json" } },
      ),
    );
    const client = new ApiClient({ baseUrl: "http://example.test", fetchImpl });

    try {
      await client.get("/ready");
      throw new Error("expected request to fail");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({ status: 503, code: "database_not_ready", requestId: "req-2" });
    }
  });
});
