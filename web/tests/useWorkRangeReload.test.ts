// @vitest-environment node
import { createRoot, createSignal } from "solid-js";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

const RANGE = {
  work_id: 781,
  corpus: "marx",
  authorSlug: "marx",
  work: "Das Kapital, Band I",
  lang: "deu",
  total: 1,
  offset: 0,
  limit: 80,
  edition: "t900",
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

const getWorkRange = vi.fn(() => Promise.resolve(RANGE));

vi.mock("~/api/readerApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("~/api/readerApi")>()),
  getWorkRange: (...args: unknown[]) => getWorkRange(...(args as [])),
  fetchOccurrenceMap: vi.fn(() =>
    Promise.resolve({ work_id: 781, lang: "deu", from: 0, limit: 80, by_chunk: {} }),
  ),
}));

vi.mock("~/api/refsApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("~/api/refsApi")>()),
  fetchReferencesMap: vi.fn(() =>
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
});
