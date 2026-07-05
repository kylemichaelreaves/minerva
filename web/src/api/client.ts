// Shared fetch helpers for all /api/* clients.

/** Error from a non-OK API response, carrying the HTTP status so
 *  callers can distinguish "this resource is gone" (404 → drop it)
 *  from transient failures (500, gateway errors → retryable; don't
 *  destroy the user's place). Network-level failures (server down,
 *  CORS, DNS) still reject with whatever `fetch` threw — only
 *  responses that arrived with an error status produce an ApiError. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** True when `err` is an HTTP-status error with the given status. */
export function isApiErrorWithStatus(err: unknown, status: number): boolean {
  return err instanceof ApiError && err.status === status;
}

/** Build a query string (`?a=1&b=x`, or `""` when nothing survives)
 *  from a params record. Skips undefined/null/empty-string values and
 *  `false`; serializes `true` as `"1"` (the backend's boolean-flag
 *  convention, e.g. `include_rejected=1`). Values are URL-encoded by
 *  URLSearchParams. */
export function qs(
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    u.set(k, v === true ? "1" : String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

export async function readErrorDetail(r: Response): Promise<string> {
  const fallback = `${r.status} ${r.statusText}`;
  // Read the body as text once, then try to interpret it. Going
  // through r.json() directly would discard a non-JSON body (proxy
  // HTML, plain-text gateway error) and lose the message.
  let raw: string;
  try {
    raw = await r.text();
  } catch {
    return fallback;
  }
  if (!raw.trim()) return fallback;
  try {
    const body = JSON.parse(raw) as { error?: unknown; detail?: unknown };
    if (typeof body.error === "string" && body.error) return body.error;
    // FastAPI reports errors under `detail` — a string, or an array of
    // {msg} for request-validation failures.
    if (typeof body.detail === "string" && body.detail) return body.detail;
    if (Array.isArray(body.detail)) {
      const msgs = body.detail
        .map((d) =>
          d && typeof d === "object" && "msg" in d
            ? String((d as { msg: unknown }).msg)
            : String(d),
        )
        .filter(Boolean);
      if (msgs.length) return msgs.join("; ");
    }
  } catch {
    // Not JSON — fall through to the trimmed text body.
  }
  const text = raw.trim();
  // A short plain-text body (e.g. a proxy's "upstream timeout") is
  // almost certainly the message; an HTML error page or an overlong
  // body is noise, so prefer the status line there.
  if (text && !text.startsWith("<") && text.length <= 500) return text;
  return fallback;
}

async function throwApiError(r: Response): Promise<never> {
  throw new ApiError(await readErrorDetail(r), r.status);
}

// Defensive: jsdom mocks with insufficient `.mockResolvedValueOnce`
// coverage (and, in principle, a polyfilled fetch) can resolve to
// `undefined`. Surface that as a real error rather than a
// `Cannot read .ok of undefined` unhandled rejection. Shared by every
// verb so the mutation helpers get the same guard as apiGet (issue #65).
function ensureResponse(r: Response | undefined, path: string): Response {
  if (!r) throw new Error(`fetch returned no response for ${path}`);
  return r;
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = ensureResponse(await fetch(path, { signal }), path);
  if (!r.ok) await throwApiError(r);
  return (await r.json()) as T;
}

export async function apiPost<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const r = ensureResponse(
    await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal,
    }),
    path,
  );
  if (!r.ok) await throwApiError(r);
  return (await r.json()) as T;
}

export async function apiPatch<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const r = ensureResponse(
    await fetch(path, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal,
    }),
    path,
  );
  if (!r.ok) await throwApiError(r);
  return (await r.json()) as T;
}

export async function apiDelete(path: string, signal?: AbortSignal): Promise<void> {
  const r = ensureResponse(await fetch(path, { method: "DELETE", signal }), path);
  if (!r.ok && r.status !== 204) await throwApiError(r);
}
