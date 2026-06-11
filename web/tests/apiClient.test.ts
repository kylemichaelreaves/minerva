import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  ApiError,
  apiGet,
  apiPost,
  isApiErrorWithStatus,
  qs,
  readErrorDetail,
} from "~/api/client";

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

  it("throws an ApiError carrying the HTTP status", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      json: () => Promise.resolve({ error: "no such conversation" }),
    } as unknown as Response);
    const err = await apiGet("/api/test").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(404);
    expect((err as ApiError).message).toBe("no such conversation");
  });
});

describe("apiPost", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("throws an ApiError carrying the HTTP status", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("not json")),
    } as unknown as Response);
    const err = await apiPost("/api/test", {}).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(500);
  });
});

describe("isApiErrorWithStatus", () => {
  it("matches only ApiError instances with the given status", () => {
    expect(isApiErrorWithStatus(new ApiError("gone", 404), 404)).toBe(true);
    expect(isApiErrorWithStatus(new ApiError("boom", 500), 404)).toBe(false);
    expect(isApiErrorWithStatus(new Error("404"), 404)).toBe(false);
    expect(isApiErrorWithStatus(undefined, 404)).toBe(false);
  });
});

describe("qs", () => {
  it("serializes defined params and skips undefined/null/empty/false", () => {
    expect(
      qs({ a: "x", b: 2, c: undefined, d: null, e: "", f: false, g: 0 }),
    ).toBe("?a=x&b=2&g=0");
  });

  it("returns the empty string when nothing survives", () => {
    expect(qs({ a: undefined, b: "" })).toBe("");
  });

  it("serializes true as the backend's '1' flag convention", () => {
    expect(qs({ include_rejected: true })).toBe("?include_rejected=1");
  });

  it("URL-encodes values", () => {
    expect(qs({ work: "Phenomenology of Spirit" })).toBe(
      "?work=Phenomenology+of+Spirit",
    );
  });
});
