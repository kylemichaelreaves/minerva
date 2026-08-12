// Response cache for the Reader's idempotent GETs.
//
// WHY THIS EXISTS
// ---------------
// `AppRoutes` renders the Reader as one `<Match>` branch of a `<Switch>`,
// so navigating to the syntax / concordance / network / refs routes
// unmounts it and destroys `useWorkRange`'s signals. Coming back remounts
// it and refetches everything, even though the corpus has not changed and
// the user was looking at that exact text a moment ago.
//
// Measured on the live index, returning from the syntax overlay: the work
// range itself is 20 ms (cheap since the 0029 index), but `occurrence_map`
// and `references_map` refire at 81 ms and 89 ms — they filter on `work_id`
// and so are still waiting on the denormalised column (#339). The three
// serialize behind the corpus lock (#340), so the return trip costs ~190 ms
// of requests for data the client already had.
//
// Module scope outlives components, which is the whole point: the cache
// survives the unmount that causes the refetch.
//
// WHAT IS SAFE TO CACHE HERE
// --------------------------
// Only GETs whose answer is a function of the corpus, which does not change
// while the SPA is open. Chunk text, term occurrences and the xref gutter
// all qualify — with one exception, handled below: references are editable
// from the refs review route, so a curation write has to drop the cached
// maps or the gutter goes stale.
//
// Deliberately NOT an in-flight promise cache. Sharing a pending request
// between callers means sharing its AbortSignal, and the Reader aborts
// aggressively on work-switch (see `useWorkRange`'s controller rotation) —
// one navigation would cancel another component's fetch. Only completed,
// successful responses are stored.

/** How many responses to keep. A work's first page plus its two companion
 *  maps is 3 entries; a few pages of `loadMore` and a couple of works fit
 *  comfortably. Small on purpose — this is a navigation cache, not a store,
 *  and chunk payloads run to hundreds of KB (one Aquinas page is 780 KB). */
const MAX_ENTRIES = 12;

const entries = new Map<string, unknown>();

/**
 * Return the cached response for `key`, or run `fetcher` and store it.
 *
 * `key` must capture every parameter that changes the answer — callers pass
 * the full request path including its query string, which does exactly that.
 */
export async function cachedRead<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  if (entries.has(key)) {
    const hit = entries.get(key) as T;
    // Re-insert to mark as recently used: Map iterates in insertion order,
    // so the eviction below takes the genuinely coldest entry.
    entries.delete(key);
    entries.set(key, hit);
    return hit;
  }

  // Awaited outside any try/catch: a rejection (including an abort) must
  // propagate to the caller untouched and must not be stored.
  const value = await fetcher();

  entries.set(key, value);
  // Walk keys in insertion order — coldest first — dropping until back at
  // the cap. Deleting during Map iteration is well-defined, and taking the
  // keys from the loop means no non-null assertion and no unreachable
  // emptiness branch. Also converges if MAX_ENTRIES is ever lowered.
  for (const coldest of entries.keys()) {
    if (entries.size <= MAX_ENTRIES) break;
    entries.delete(coldest);
  }
  return value;
}

/**
 * Drop cached responses whose key contains `substring`, or everything when
 * called with no argument.
 *
 * Used by the reference-curation write: accepting or rejecting an xref in
 * the refs route changes what `references_map` would return, and without
 * this the Reader's gutter would keep showing the pre-edit markers for the
 * rest of the session.
 */
export function invalidateReads(substring?: string): void {
  if (substring === undefined) {
    entries.clear();
    return;
  }
  for (const key of [...entries.keys()]) {
    if (key.includes(substring)) entries.delete(key);
  }
}

/** Entry count. Exported for tests — nothing in the app should need it. */
export function cachedReadCount(): number {
  return entries.size;
}
