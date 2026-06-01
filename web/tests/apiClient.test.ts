import { describe, it, expect, vi, beforeEach } from "vitest";
import { readErrorDetail, apiGet } from "~/api/client";

describe("readErrorDetail", () => {
  it("returns JSON error body when present", async () => {
    const r = {
      status: 404,
      statusText: "Not Found",
      json: () => Promise.resolve({ error: "unknown chunk_id" }),
    } as unknown as Response;
    expect(await readErrorDetail(r)).toBe("unknown chunk_id");
  });

  it("falls back to status text when body is not JSON", async () => {
    const r = {
      status: 502,
      statusText: "Bad Gateway",
      json: () => Promise.reject(new Error("not json")),
    } as unknown as Response;
    expect(await readErrorDetail(r)).toBe("502 Bad Gateway");
  });
});

describe("apiGet", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("throws with server error detail on failure", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 400,
      statusText: "Bad Request",
      json: () => Promise.resolve({ error: "invalid limit" }),
    } as unknown as Response);
    await expect(apiGet("/api/test")).rejects.toThrow("invalid limit");
  });
});
