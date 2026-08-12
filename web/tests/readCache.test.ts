/**
 * The Reader's route-switch cache.
 *
 * `AppRoutes` unmounts the Reader when any other route matches, so returning
 * to it refetches the window the user was already looking at — ~190 ms of
 * requests, mostly the two companion maps. These tests pin the properties
 * that make caching it safe: keys carry every parameter, failures are never
 * stored, and a curation write drops the maps it invalidates.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { cachedRead, cachedReadCount, invalidateReads } from "~/api/readCache";
import { getWorkRange, fetchOccurrenceMap } from "~/api/readerApi";
import { fetchReferencesMap, updateReferenceCuration } from "~/api/refsApi";

beforeEach(() => {
  invalidateReads();
});

describe("cachedRead", () => {
  it("runs the fetcher once and serves the second call from cache", async () => {
    const fetcher = vi.fn().mockResolvedValue({ chunks: ["a"] });

    const first = await cachedRead("/api/works/Ethica?from=0&limit=80", fetcher);
    const second = await cachedRead("/api/works/Ethica?from=0&limit=80", fetcher);

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(second).toBe(first);
  });

  it("treats different query strings as different entries", async () => {
    // The return trip from the syntax overlay asks `around=…&limit=200`
    // where the original load asked `from=0&limit=80`. Same work, different
    // answer — a key that ignored the query would serve the wrong window.
    const fetcher = vi.fn().mockResolvedValueOnce({ n: 1 }).mockResolvedValueOnce({ n: 2 });

    const page = await cachedRead("/api/works/Ethica?from=0&limit=80", fetcher);
    const focus = await cachedRead("/api/works/Ethica?around=abc&limit=200", fetcher);

    expect(fetcher).toHaveBeenCalledTimes(2);
    expect(page).not.toEqual(focus);
  });

  it("does not cache a rejection", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce({ ok: true });

    await expect(cachedRead("/api/works/Ethica", fetcher)).rejects.toThrow("network down");
    // A stored rejection would make the failure permanent for the session.
    await expect(cachedRead("/api/works/Ethica", fetcher)).resolves.toEqual({ ok: true });
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("does not cache an aborted request", async () => {
    // `useWorkRange` aborts on work-switch. An abort is not an answer.
    const abort = Object.assign(new Error("aborted"), { name: "AbortError" });
    const fetcher = vi.fn().mockRejectedValueOnce(abort).mockResolvedValueOnce({ ok: true });

    await expect(cachedRead("/api/works/Iliad", fetcher)).rejects.toThrow("aborted");

    expect(cachedReadCount()).toBe(0);
    await expect(cachedRead("/api/works/Iliad", fetcher)).resolves.toEqual({ ok: true });
  });

  it("evicts the coldest entry past the cap", async () => {
    for (let i = 0; i < 12; i++) {
      await cachedRead(`/key-${i}`, () => Promise.resolve(i));
    }
    expect(cachedReadCount()).toBe(12);

    // Touch the oldest so it is no longer coldest, then overflow by one.
    await cachedRead("/key-0", () => Promise.resolve(-1));
    await cachedRead("/key-12", () => Promise.resolve(12));

    expect(cachedReadCount()).toBe(12);
    // key-0 survived because it was touched; key-1 was next-coldest.
    const refetch = vi.fn().mockResolvedValue(99);
    await cachedRead("/key-0", refetch);
    expect(refetch).not.toHaveBeenCalled();
    await cachedRead("/key-1", refetch);
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

describe("the reader GETs are actually wired to the cache", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  function json(body: unknown): Response {
    return { ok: true, status: 200, json: () => Promise.resolve(body) } as unknown as Response;
  }

  beforeEach(() => {
    fetchMock = vi.fn().mockResolvedValue(json({ by_chunk: {} }));
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("serves a repeat work-range load without hitting the network", async () => {
    await getWorkRange("Ethica", { author: "Spinoza", from: 0, limit: 80 });
    await getWorkRange("Ethica", { author: "Spinoza", from: 0, limit: 80 });

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("serves repeat companion maps without hitting the network", async () => {
    await fetchOccurrenceMap(5, { lang: "lat", from: 0, limit: 80 });
    await fetchReferencesMap(5, { lang: "lat", from: 0, limit: 80 });
    await fetchOccurrenceMap(5, { lang: "lat", from: 0, limit: 80 });
    await fetchReferencesMap(5, { lang: "lat", from: 0, limit: 80 });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("refetches the xref gutter after a curation write", async () => {
    await fetchReferencesMap(5, { lang: "lat", from: 0, limit: 80 });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await updateReferenceCuration(42, { curator_status: "rejected" });
    await fetchReferencesMap(5, { lang: "lat", from: 0, limit: 80 });

    // PATCH + the refetch the invalidation forced.
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("leaves the occurrence map cached across a curation write", async () => {
    await fetchOccurrenceMap(5, { lang: "lat", from: 0, limit: 80 });
    await updateReferenceCuration(42, { curator_status: "approved" });
    await fetchOccurrenceMap(5, { lang: "lat", from: 0, limit: 80 });

    // The initial GET and the PATCH — the second GET was a cache hit.
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("invalidateReads", () => {
  it("drops only the matching keys", async () => {
    await cachedRead("/api/works/5/references_map?from=0", () => Promise.resolve("refs"));
    await cachedRead("/api/works/5/occurrence_map?from=0", () => Promise.resolve("occ"));
    await cachedRead("/api/works/Ethica?from=0", () => Promise.resolve("range"));

    invalidateReads("/references_map");

    expect(cachedReadCount()).toBe(2);
    const refetch = vi.fn().mockResolvedValue("fresh");
    await cachedRead("/api/works/5/references_map?from=0", refetch);
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("clears everything when given no argument", async () => {
    await cachedRead("/a", () => Promise.resolve(1));
    await cachedRead("/b", () => Promise.resolve(2));

    invalidateReads();

    expect(cachedReadCount()).toBe(0);
  });
});
