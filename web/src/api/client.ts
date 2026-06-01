// Shared fetch helpers for all /api/* clients.

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

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const r = await fetch(path, { signal });
  // Defensive: jsdom mocks with insufficient `.mockResolvedValueOnce`
  // coverage can yield `undefined` here. Surface as a real error
  // instead of a `Cannot read .ok of undefined` unhandled rejection.
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  if (!r) throw new Error(`fetch returned no response for ${path}`);
  if (!r.ok) throw new Error(await readErrorDetail(r));
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
  if (!r.ok) throw new Error(await readErrorDetail(r));
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
  if (!r.ok) throw new Error(await readErrorDetail(r));
  return (await r.json()) as T;
}

export async function apiDelete(path: string, signal?: AbortSignal): Promise<void> {
  const r = await fetch(path, { method: "DELETE", signal });
  if (!r.ok && r.status !== 204) throw new Error(await readErrorDetail(r));
}
