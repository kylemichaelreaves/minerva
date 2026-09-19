import { afterEach, beforeEach, describe, expect, it, vi, type MockedFunction } from "vitest";
import { createRoot } from "solid-js";
import { useReader } from "~/Reader/readerCtrl";
import { _resetToastsForTesting } from "~/utils/apiError";
import type { Work } from "~/utils/types";
import { createTestRouting, flush, okResponse } from "./helpers/testRouting";

/** Reader navigation under slug routes (#602). */

let fetchMock: MockedFunction<typeof fetch>;

const WORKS: Work[] = [
  {
    work_id: 1,
    corpus: "nietzsche",
    author: "Nietzsche",
    work: "Die fröhliche Wissenschaft",
    lang: "deu",
    chunks: 100,
    display_title: "Die fröhliche Wissenschaft",
  },
];

function runReader(routing = createTestRouting()) {
  let api!: ReturnType<typeof useReader>;
  const dispose = createRoot((d) => {
    api = useReader(routing, vi.fn());
    return d;
  });
  return { api, routing, dispose };
}

describe("navigation emits slugs", () => {
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

  it("openWork navigates to the author/title slug pair with no round-trip", async () => {
    // `openWork` is handed the whole `Work`, so it already holds the author
    // and the title and can slugify both locally. Putting an `/api/works`
    // fetch in front of navigation is the #428 shape and is what the
    // server-side resolution exists to avoid.
    const { api, routing, dispose } = runReader();
    const work = WORKS[0];
    if (work === undefined) throw new Error("fixture");
    api.openWork(work);
    await flush();
    expect(routing.route()).toMatchObject({
      kind: "reader",
      authorSlug: "nietzsche",
      workSlug: "die-frohliche-wissenschaft",
      sourceLang: "deu",
    });
    dispose();
  });

  it("openAtChunk emits a title slug and no author", async () => {
    // A citation deep-link has a title and a chunk and nothing else. The
    // server resolves work, lang and edition off `around=<chunk>`.
    const { api, routing, dispose } = runReader();
    api.openAtChunk("Die fröhliche Wissenschaft", undefined, "fw-125");
    await flush();
    expect(routing.route()).toMatchObject({
      kind: "reader",
      workSlug: "die-frohliche-wissenschaft",
      focusChunkId: "fw-125",
    });
    expect((routing.route() as { authorSlug?: string }).authorSlug).toBeUndefined();
    dispose();
  });

  it("currentWork matches the works list through the slug, not the raw title", async () => {
    const routing = createTestRouting({
      kind: "reader",
      authorSlug: "nietzsche",
      workSlug: "die-frohliche-wissenschaft",
      sourceLang: "deu",
    });
    const { api, dispose } = runReader(routing);
    await api.ensureWorks();
    await flush();
    expect(api.currentWork()?.work).toBe("Die fröhliche Wissenschaft");
    dispose();
  });

  it("restores a PRE-SLUG remembered location, which holds raw titles", async () => {
    // `minerva:last-reader` blobs written before this change carry `workId`
    // and `author` as titles. Slugifying whatever is there is what keeps a
    // returning user's Chat → Read round-trip landing on their passage
    // instead of silently falling back to the first Greek work.
    localStorage.setItem(
      "minerva:last-reader",
      JSON.stringify({
        workId: "Die fröhliche Wissenschaft",
        sourceLang: "deu",
        author: "Nietzsche",
      }),
    );
    const { api, routing, dispose } = runReader();
    await api.switchMode("reader");
    await flush();
    expect(routing.route()).toMatchObject({
      kind: "reader",
      authorSlug: "nietzsche",
      workSlug: "die-frohliche-wissenschaft",
    });
    dispose();
  });
});
