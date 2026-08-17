import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "./client";

describe("active Site API contract", () => {
  it("can send an explicit bearer token without storing it in global API configuration", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ id: "site-1" }), { status: 200, headers: { "content-type": "application/json" } }));
    const client = new ApiClient({ baseUrl: "http://example.test", fetchImpl });
    await client.get("/api/v1/projects/p1/sites/active", { headers: { Authorization: "Bearer secret-token" } });
    expect(fetchImpl).toHaveBeenCalledWith("http://example.test/api/v1/projects/p1/sites/active", expect.objectContaining({ headers: expect.objectContaining({ Authorization: "Bearer secret-token" }) }));
  });
});
