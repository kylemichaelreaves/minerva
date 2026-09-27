import { describe, it, expect, beforeEach, afterEach, vi, type MockedFunction } from "vitest";
import { createRoot } from "solid-js";
import { useReader } from "~/Reader/readerCtrl";
import { _resetToastsForTesting, useToasts } from "~/utils/apiError";
import type { Work } from "~/utils/types";
import { createTestRouting, flush, okResponse } from "./helpers/testRouting";
import { must } from "./helpers/must";

let fetchMock: MockedFunction<typeof fetch>;

const WORKS: Work[] = [
  {
    work_id: 1,
    corpus: "plato",
    author: "Plato",
    work: "Republic",
    lang: "grc",
    chunks: 100,
    display_title: "Republic",
  },
  {
    work_id: 2,
    corpus: "plato",
    author: "Plato",
    work: "Republic",
    lang: "eng",
    chunks: 80,
    display_title: "Republic (English)",
  },
];

function runReader(routing = createTestRouting(), abortChat: () => void = vi.fn()) {
  let api!: ReturnType<typeof useReader>;
  const dispose = createRoot((d) => {
    api = useReader(routing, abortChat);
    return d;
  });
  return { api, routing, dispose, abortChat };
}

describe("useReader()", () => {
  beforeEach(() => {
    localStorage.clear();
    _resetToastsForTesting();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValue(okResponse({ works: WORKS }));
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("readerWork is null on landing and mode is chat", async () => {
    const { api, dispose } = runReader();
    await flush();
    expect(api.readerWork()).toBeNull();
    expect(api.mode()).toBe("chat");
    dispose();
  });

  it("readerWork reflects the reader route", async () => {
    const routing = createTestRouting({
      kind: "reader",
      workSlug: "republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
    });
    const { api, dispose } = runReader(routing);
    await flush();
    expect(api.readerWork()).toEqual({
      workSlug: "republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
      openTermId: undefined,
    });
    expect(api.mode()).toBe("reader");
    dispose();
  });

  it("currentWork resolves against loaded works", async () => {
    const routing = createTestRouting({
      kind: "reader",
      workSlug: "republic",
      sourceLang: "grc",
    });
    const { api, dispose } = runReader(routing);
    await api.ensureWorks();
    await flush();
    await flush();
    expect(api.currentWork()?.lang).toBe("grc");
    dispose();
  });

  it("openAtChunk aborts chat and navigates with focus", () => {
    const abortChat = vi.fn();
    const routing = createTestRouting({ kind: "landing" });
    const { api, routing: r, dispose } = runReader(routing, abortChat);
    api.openAtChunk("Republic", "grc", "rep-509d");
    expect(abortChat).toHaveBeenCalled();
    expect(r.navigateSpy).toHaveBeenCalledWith({
      kind: "reader",
      workSlug: "republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
    });
    dispose();
  });

  it("openWork navigates to the selected work", () => {
    const abortChat = vi.fn();
    const { api, routing: r, dispose } = runReader(createTestRouting(), abortChat);
    api.openWork(must(WORKS[1]));
    expect(abortChat).toHaveBeenCalled();
    expect(r.navigateSpy).toHaveBeenCalledWith({
      kind: "reader",
      workSlug: "republic",
      sourceLang: "eng",
      authorSlug: "plato",
    });
    dispose();
  });

  it("setOpenTermId updates the reader route term param", () => {
    const routing = createTestRouting({
      kind: "reader",
      workSlug: "republic",
      sourceLang: "grc",
    });
    const { api, routing: r, dispose } = runReader(routing);
    api.setOpenTermId(42);
    expect(r.navigateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "reader", openTermId: 42 }),
    );
    dispose();
  });

  it("setOpenTermId is a no-op off the reader route", () => {
    const routing = createTestRouting({ kind: "landing" });
    const { api, routing: r, dispose } = runReader(routing);
    api.setOpenTermId(42);
    expect(r.navigateSpy).not.toHaveBeenCalled();
    dispose();
  });

  it("switchMode to chat restores last conversation from localStorage", async () => {
    localStorage.setItem("minerva:last-conversation", "thread-9");
    const routing = createTestRouting({
      kind: "reader",
      workSlug: "republic",
      sourceLang: "grc",
    });
    const { api, routing: r, dispose } = runReader(routing);
    await api.switchMode("chat");
    expect(r.navigateSpy).toHaveBeenCalledWith({ kind: "conversation", id: "thread-9" });
    dispose();
  });

  it("switchMode to chat falls back to landing without a saved conversation", async () => {
    const routing = createTestRouting({
      kind: "reader",
      workSlug: "republic",
      sourceLang: "grc",
    });
    const { api, routing: r, dispose } = runReader(routing);
    await api.switchMode("chat");
    expect(r.navigateSpy).toHaveBeenCalledWith({ kind: "landing" });
    dispose();
  });

  it("switchMode to reader uses remembered location from localStorage", async () => {
    localStorage.setItem(
      "minerva:last-reader",
      JSON.stringify({ workSlug: "republic", sourceLang: "eng" }),
    );
    const { api, routing: r, dispose } = runReader();
    await api.switchMode("reader");
    expect(r.navigateSpy).toHaveBeenCalledWith({
      kind: "reader",
      workSlug: "republic",
      sourceLang: "eng",
    });
    dispose();
  });

  it("switchMode to reader picks the first Greek work when nothing is remembered", async () => {
    const { api, routing: r, dispose } = runReader();
    await api.switchMode("reader");
    await flush();
    expect(r.navigateSpy).toHaveBeenCalledWith({
      kind: "reader",
      workSlug: "republic",
      sourceLang: "grc",
      authorSlug: "plato",
    });
    dispose();
  });

  it("switchMode is a no-op when already in the target mode", async () => {
    const routing = createTestRouting({ kind: "landing" });
    const { api, routing: r, dispose } = runReader(routing);
    await api.switchMode("chat");
    expect(r.navigateSpy).not.toHaveBeenCalled();
    dispose();
  });

  it("empty works list surfaces apiError", async () => {
    fetchMock.mockResolvedValue(okResponse({ works: [] }));
    const { api, dispose } = runReader();
    await api.switchMode("reader");
    await flush();
    expect(useToasts()().some((t) => t.message.includes("No works"))).toBe(true);
    dispose();
  });

  it("ensureWorks is single-flight", async () => {
    const { api, dispose } = runReader();
    const a = api.ensureWorks();
    const b = api.ensureWorks();
    expect(a).toBe(b);
    await a;
    await flush();
    expect(
      fetchMock.mock.calls.filter((c) => (c[0] as string).includes("/api/works")),
    ).toHaveLength(1);
    dispose();
  });

  it("persists reader location and conversation id to localStorage", async () => {
    const routing = createTestRouting({
      kind: "reader",
      workSlug: "republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
    });
    const { dispose } = runReader(routing);
    await flush();
    expect(JSON.parse(localStorage.getItem("minerva:last-reader") ?? "{}")).toMatchObject({
      workSlug: "republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
    });

    routing.setRoute({ kind: "conversation", id: "saved-thread" });
    await flush();
    expect(localStorage.getItem("minerva:last-conversation")).toBe("saved-thread");
    dispose();
  });
  describe("resolveWork — surviving the /api/works round-trip (#428)", () => {
    // Both Reader exits seed the chat scope from `currentWork()`, which
    // resolves the route against the LAZILY-loaded `works()` list while the
    // Reader itself renders from the route. Leaving inside that round-trip
    // therefore seeded `null` and silently dropped the work — the exact
    // outcome #350 set out to stop.
    //
    // Note what this does NOT claim to fix by retaining alone: if the list
    // never loaded, nothing was ever resolved, so there is nothing retained
    // to fall back on. `resolveWork` closes it by awaiting the single-flight
    // loader instead, which is why it returns a promise.
    const READER_ROUTE = {
      kind: "reader" as const,
      workSlug: "republic",
      sourceLang: "grc",
    };

    it("resolves the Work once the list arrives, from a cold works() list", async () => {
      // Hold /api/works open so `works()` is still empty when we ask.
      let release: (() => void) | undefined;
      const gate = new Promise<void>((r) => {
        release = r;
      });
      fetchMock.mockImplementation(async () => {
        await gate;
        return okResponse({ works: WORKS });
      });

      const routing = createTestRouting(READER_ROUTE);
      const { api, dispose } = runReader(routing);
      await flush();

      // The pre-existing accessor cannot answer yet — this is the defect.
      expect(api.works()).toEqual([]);
      expect(api.currentWork()).toBeNull();

      const loc = api.readerWork();
      expect(loc).not.toBeNull();
      const pending = api.resolveWork(must(loc));

      must(release)();
      await expect(pending).resolves.toMatchObject({
        work_id: 1,
        display_title: "Republic",
      });
      dispose();
    });

    it("returns the same Work currentWork() would, once warm", async () => {
      const routing = createTestRouting(READER_ROUTE);
      const { api, dispose } = runReader(routing);
      await flush();
      await api.ensureWorks();
      const direct = api.currentWork();
      expect(direct).not.toBeNull();
      await expect(api.resolveWork(must(api.readerWork()))).resolves.toEqual(direct);
      dispose();
    });

    it("honours sourceLang so it does not return the wrong edition", async () => {
      // `Republic` exists in grc and eng; the scope must get the one being read.
      const routing = createTestRouting({ ...READER_ROUTE, sourceLang: "eng" });
      const { api, dispose } = runReader(routing);
      await flush();
      await expect(api.resolveWork(must(api.readerWork()))).resolves.toMatchObject({
        work_id: 2,
        lang: "eng",
      });
      dispose();
    });

    it("resolves null for a location with no matching work", async () => {
      const routing = createTestRouting({
        kind: "reader",
        workSlug: "nonexistent",
        sourceLang: "grc",
      });
      const { api, dispose } = runReader(routing);
      await flush();
      await expect(api.resolveWork(must(api.readerWork()))).resolves.toBeNull();
      dispose();
    });

    it("resolves null rather than rejecting when the works fetch fails", async () => {
      // A failed list must not turn an exit gesture into an unhandled
      // rejection — the caller's job is to leave the scope alone.
      fetchMock.mockRejectedValue(new Error("offline"));
      const routing = createTestRouting(READER_ROUTE);
      const { api, dispose } = runReader(routing);
      await flush();
      await expect(api.resolveWork(must(api.readerWork()))).resolves.toBeNull();
      dispose();
    });
  });
});
