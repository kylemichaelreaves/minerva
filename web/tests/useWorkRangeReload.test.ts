// @vitest-environment node
import { createRoot, createSignal } from "solid-js";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type * as readerApi from "~/api/readerApi";
import type { WorkRange } from "~/api/types/reader";
import type * as refsApi from "~/api/refsApi";
import { useWorkRange } from "~/Reader/useWorkRange";
import type { Route } from "~/routing";

// When `useWorkRange` reloads, and when it must not.
//
// The hook's load effect reads `props.workId` / `sourceLang` / `author` /
// `focusChunkId`, and in the app every one of those reads goes through the
// route signal (`ReaderRoute` passes `readerWork()!.workId` and friends as JSX
// props, which Solid compiles to getters). A signal notifies on identity, so
// `setRoute(readRoute())` — a NEW Route object on every hashchange — re-runs
// the effect even when all four values are character-for-character the same.
//
// That is what makes a route modifier expensive: adding `?syntax=…` or
// `?term=…` to the URL does not change the window, but it does replace the
// route object, and the reload begins with `setRange(null)` — the blank frame
// #342 is about.

const RANGE: WorkRange = {
  work_id: 781,
  corpus: "marx",
  author: "Marx",
  work: "Das Kapital, Band I",
  display_title: "Das Kapital, Band I",
  lang: "deu",
  total: 1,
  offset: 0,
  limit: 80,
  edition: "t900",
  editions: [],
  chunks: [
    {
      chunk_id: "k-1",
      section: "1",
      book: null,
      page: null,
      speaker: null,
      text: "Die Ware.",
      ord: 0,
    },
  ],
};

const getWorkRange = vi.fn<typeof readerApi.getWorkRange>(() => Promise.resolve(RANGE));

vi.mock("~/api/readerApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("~/api/readerApi")>()),
  getWorkRange: (...args: Parameters<typeof readerApi.getWorkRange>) => getWorkRange(...args),
  fetchOccurrenceMap: vi.fn<typeof readerApi.fetchOccurrenceMap>(() =>
    Promise.resolve({ work_id: 781, lang: "deu", from: 0, limit: 80, by_chunk: {} }),
  ),
}));

vi.mock("~/api/refsApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("~/api/refsApi")>()),
  fetchReferencesMap: vi.fn<typeof refsApi.fetchReferencesMap>(() =>
    Promise.resolve({ work_id: 781, lang: "deu", from: 0, limit: 80, by_chunk: {} }),
  ),
}));

const READER: Route = { kind: "reader", workSlug: "das-kapital-band-i", sourceLang: "deu" };

/** Mount the hook behind route-derived getters, exactly as `ReaderRoute`
 *  does, so the effect subscribes to the route signal rather than to four
 *  independent props. */
function mount(initial: Route = READER) {
  const [route, setRoute] = createSignal<Route>(initial);
  const loc = () => {
    const r = route();
    return r.kind === "reader" ? r : null;
  };
  let dispose = (): void => undefined;
  createRoot((d) => {
    dispose = d;
    useWorkRange(
      {
        get workSlug() {
          return loc()?.workSlug ?? "";
        },
        get sourceLang() {
          return loc()?.sourceLang;
        },
        get authorSlug() {
          return loc()?.authorSlug;
        },
        get focusChunkId() {
          return loc()?.focusChunkId;
        },
      },
      () => undefined,
    );
  });
  return { setRoute, dispose };
}

const settle = async (): Promise<void> => {
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
};

describe("useWorkRange reload policy", () => {
  beforeEach(() => {
    getWorkRange.mockClear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads the window once on mount", async () => {
    const { dispose } = mount();
    await settle();
    expect(getWorkRange).toHaveBeenCalledTimes(1);
    dispose();
  });

  it("does not reload when the route object changes but the window does not", async () => {
    const { setRoute, dispose } = mount();
    await settle();
    expect(getWorkRange).toHaveBeenCalledTimes(1);

    // A fresh object with identical window fields — what every hashchange
    // produces, and what opening the syntax layer or a term card produces.
    setRoute({ ...READER, openTermId: 42 });
    await settle();

    expect(getWorkRange).toHaveBeenCalledTimes(1);
    dispose();
  });

  it("reloads when the work changes", async () => {
    const { setRoute, dispose } = mount();
    await settle();

    setRoute({ kind: "reader", workSlug: "das-kapital-band-ii", sourceLang: "deu" });
    await settle();

    expect(getWorkRange).toHaveBeenCalledTimes(2);
    dispose();
  });

  it("reloads when the focused chunk changes", async () => {
    const { setRoute, dispose } = mount();
    await settle();

    setRoute({ ...READER, focusChunkId: "k-9" });
    await settle();

    expect(getWorkRange).toHaveBeenCalledTimes(2);
    dispose();
  });

  // #611: a one-segment URL grows the author segment its range named. That
  // author is read off the response, so it cannot change which edition loads.
  it("does not reload when the route grows the author the loaded range named", async () => {
    const { setRoute, dispose } = mount();
    await settle();

    setRoute({ ...READER, authorSlug: "marx" });
    await settle();
    // And a later modifier on the grown route is still not a change of window.
    setRoute({ ...READER, authorSlug: "marx", openTermId: 42 });
    await settle();

    expect(getWorkRange).toHaveBeenCalledTimes(1);
    dispose();
  });

  it("reloads when the route gains an author the range did not name", async () => {
    const { setRoute, dispose } = mount();
    await settle();

    setRoute({ ...READER, authorSlug: "engels" });
    await settle();

    expect(getWorkRange).toHaveBeenCalledTimes(2);
    dispose();
  });

  it("reloads when an author arrives before any range has loaded", async () => {
    const { setRoute, dispose } = mount();
    // No settle: the first load is still in flight, so nothing has named an
    // author yet and this one came from somewhere else.
    setRoute({ ...READER, authorSlug: "marx" });
    await settle();

    expect(getWorkRange).toHaveBeenCalledTimes(2);
    dispose();
  });

  it("reloads when the author changes between two named authors", async () => {
    const { setRoute, dispose } = mount({ ...READER, authorSlug: "marx" });
    await settle();

    setRoute({ ...READER, authorSlug: "engels" });
    await settle();

    expect(getWorkRange).toHaveBeenCalledTimes(2);
    dispose();
  });
});
