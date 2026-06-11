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
  let detail = `${r.status} ${r.statusText}`;
  try {
    const body = (await r.json()) as { error?: string };
    if (body.error) detail = body.error;
  } catch {
    // body wasn't JSON
  }
  return detail;
}

async function throwApiError(r: Response): Promise<never> {
  throw new ApiError(await readErrorDetail(r), r.status);
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, { signal });
  // Defensive: jsdom mocks with insufficient `.mockResolvedValueOnce`
  // coverage can yield `undefined` here. Surface as a real error
  // instead of a `Cannot read .ok of undefined` unhandled rejection.
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  if (!r) throw new Error(`fetch returned no response for ${path}`);
  if (!r.ok) await throwApiError(r);
  return (await r.json()) as T;
}

export async function apiPost<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const r = await fetch(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok) await throwApiError(r);
  return (await r.json()) as T;
}

export async function apiPatch<T>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  const r = await fetch(path, {
    method: "PATCH",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok) await throwApiError(r);
  return (await r.json()) as T;
}

export async function apiDelete(path: string, signal?: AbortSignal): Promise<void> {
  const r = await fetch(path, { method: "DELETE", signal });
  if (!r.ok && r.status !== 204) await throwApiError(r);
}
