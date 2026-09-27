// @vitest-environment node
import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  ApiError,
  apiGet,
  apiPost,
  isApiErrorWithStatus,
  qs,
  readErrorDetail,
} from "~/api/client";

function resp(status: number, statusText: string, bodyText: string): Response {
  return {
    status,
    statusText,
    text: () => Promise.resolve(bodyText),
  } as unknown as Response;
}

describe("readErrorDetail", () => {
  it("returns JSON error body when present", async () => {
    const r = resp(404, "Not Found", JSON.stringify({ error: "unknown chunk_id" }));
    expect(await readErrorDetail(r)).toBe("unknown chunk_id");
  });

  it("returns FastAPI {detail} string", async () => {
    const r = resp(422, "Unprocessable", JSON.stringify({ detail: "bad work id" }));
    expect(await readErrorDetail(r)).toBe("bad work id");
  });

  it("joins FastAPI validation {detail:[{msg}]} array", async () => {
    const r = resp(
      422,
      "Unprocessable",
      JSON.stringify({ detail: [{ msg: "field required" }, { msg: "too big" }] }),
    );
    expect(await readErrorDetail(r)).toBe("field required; too big");
  });

  it("surfaces a short plain-text (proxy) body", async () => {
    const r = resp(504, "Gateway Timeout", "upstream timeout");
    expect(await readErrorDetail(r)).toBe("upstream timeout");
  });

  it("falls back to status text for an HTML error page", async () => {
    const r = resp(502, "Bad Gateway", "<html><body>502</body></html>");
    expect(await readErrorDetail(r)).toBe("502 Bad Gateway");
  });

  it("falls back to status text for an empty body", async () => {
    const r = resp(500, "Internal Server Error", "");
    expect(await readErrorDetail(r)).toBe("500 Internal Server Error");
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
      text: () => Promise.resolve(JSON.stringify({ error: "invalid limit" })),
    } as unknown as Response);
    await expect(apiGet("/api/test")).rejects.toThrow("invalid limit");
  });

  it("throws an ApiError carrying the HTTP status", async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      text: () => Promise.resolve(JSON.stringify({ error: "no such conversation" })),
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
      text: () => Promise.resolve(""),
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
