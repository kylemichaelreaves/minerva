import { describe, it, expect, beforeEach, afterEach, vi, type MockedFunction } from "vitest";
import { createRoot } from "solid-js";
import { useReader } from "~/Reader/readerCtrl";
import { _resetToastsForTesting, useToasts } from "~/utils/apiError";
import type { Work } from "~/utils/types";
import { createTestRouting, flush, okResponse } from "./helpers/testRouting";

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

function runReader(
  routing = createTestRouting(),
  abortChat: () => void = vi.fn(),
) {
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
      workId: "Republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
    });
    const { api, dispose } = runReader(routing);
    await flush();
    expect(api.readerWork()).toEqual({
      workId: "Republic",
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
      workId: "Republic",
      sourceLang: "grc",
    });
    const { api, dispose } = runReader(routing);
    await api.ensureWorks();
    await flush();
    await flush();
    expect(api.currentWork()?.lang).toBe("grc");
    dispose();
  });

  it("openAtChunk aborts chat and navigates with focus", async () => {
    const abortChat = vi.fn();
    const routing = createTestRouting({ kind: "landing" });
    const { api, routing: r, dispose } = runReader(routing, abortChat);
    api.openAtChunk("Republic", "grc", "rep-509d");
    expect(abortChat).toHaveBeenCalled();
    expect(r.navigateSpy).toHaveBeenCalledWith({
      kind: "reader",
      workId: "Republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
    });
    dispose();
  });

  it("openWork navigates to the selected work", async () => {
    const abortChat = vi.fn();
    const { api, routing: r, dispose } = runReader(createTestRouting(), abortChat);
    api.openWork(WORKS[1]!);
    expect(abortChat).toHaveBeenCalled();
    expect(r.navigateSpy).toHaveBeenCalledWith({
      kind: "reader",
      workId: "Republic",
      sourceLang: "eng",
    });
    dispose();
  });

  it("setOpenTermId updates the reader route term param", async () => {
    const routing = createTestRouting({
      kind: "reader",
      workId: "Republic",
      sourceLang: "grc",
    });
    const { api, routing: r, dispose } = runReader(routing);
    api.setOpenTermId(42);
    expect(r.navigateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "reader", openTermId: 42 }),
    );
    dispose();
  });

  it("setOpenTermId is a no-op off the reader route", async () => {
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
      workId: "Republic",
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
      workId: "Republic",
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
      JSON.stringify({ workId: "Republic", sourceLang: "eng" }),
    );
    const { api, routing: r, dispose } = runReader();
    await api.switchMode("reader");
    expect(r.navigateSpy).toHaveBeenCalledWith({
      kind: "reader",
      workId: "Republic",
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
      workId: "Republic",
      sourceLang: "grc",
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
    expect(fetchMock.mock.calls.filter((c) => String(c[0]).includes("/api/works"))).toHaveLength(
      1,
    );
    dispose();
  });

  it("persists reader location and conversation id to localStorage", async () => {
    const routing = createTestRouting({
      kind: "reader",
      workId: "Republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
    });
    const { dispose } = runReader(routing);
    await flush();
    expect(JSON.parse(localStorage.getItem("minerva:last-reader") ?? "{}")).toMatchObject({
      workId: "Republic",
      sourceLang: "grc",
      focusChunkId: "rep-509d",
    });

    routing.setRoute({ kind: "conversation", id: "saved-thread" });
    await flush();
    expect(localStorage.getItem("minerva:last-conversation")).toBe("saved-thread");
    dispose();
  });
});
