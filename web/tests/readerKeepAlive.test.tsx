import { fireEvent, render, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi, type MockedFunction } from "vitest";
import App from "~/App";
import { invalidateReads } from "~/api/readCache";
import { _resetToastsForTesting } from "~/utils/apiError";
import { okResponse } from "./helpers/testRouting";
import { must } from "./helpers/must";

// The concordance is a step-out from the Reader, not a destination (#348).
//
// #342 fixed the syntax overlay by making it a modifier on the reader route;
// the other three side routes stayed peer `<Match>` branches, so each one
// still unmounted the Reader — `useWorkRange`'s signals destroyed, the window
// refetched, scroll position and card / rail / selection state gone. The
// entry-point evidence splits them: `Reader/index.tsx` links into the
// concordance twice (the rail's lemma card and the work-concordance link) and
// never into the network dashboard or the refs browser, which are reached from
// the top nav. So the concordance keeps the Reader alive underneath; network
// and refs stay full-page destinations that release it.
//
// As with the syntax layer these assertions are node identity, never fetch
// counts: a cached read from #343 serves a refetch without touching `fetch`,
// so a count would pass while the Reader was still being torn down and rebuilt.

const RANGE = {
  work_id: 781,
  corpus: "marx",
  author: "Marx",
  work: "Das Kapital, Band I",
  lang: "deu",
  total: 2,
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
      text: "Die Ware ist zunächst ein äußerer Gegenstand.",
      ord: 0,
    },
    {
      chunk_id: "k-2",
      section: "2",
      book: null,
      page: null,
      speaker: null,
      text: "Der Gebrauchswert verwirklicht sich nur im Gebrauch.",
      ord: 1,
    },
  ],
};

const READER_HASH = "#/r/Das%20Kapital%2C%20Band%20I?lang=deu";
const LEMMA_HASH = "#/concordance/Ware";
const INDEX_HASH = "#/concordance?lang=deu";

let fetchMock: MockedFunction<typeof fetch>;

/** Drive the hash the way the browser's back/forward buttons do — the app
 *  reads the URL on popstate and never writes history from an effect. */
function go(hash: string): void {
  window.history.pushState(null, "", hash);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

/** The keep-alive wrapper, or null when no Reader is retained at all. */
function keepAlive(): Element | null {
  return document.querySelector(".reader-keepalive");
}

describe("the concordance as a step-out that keeps the Reader mounted", () => {
  beforeEach(() => {
    localStorage.clear();
    _resetToastsForTesting();
    // The read cache is module scope on purpose (it has to outlive
    // components), so it also outlives a test. Clear it so each case starts
    // cold and one case's window cannot answer another's.
    invalidateReads();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("occurrence_map") || url.includes("references_map")) {
        return Promise.resolve(okResponse({ work_id: 781, lang: "deu", by_chunk: {} }));
      }
      if (url.includes("/api/works/")) return Promise.resolve(okResponse(RANGE));
      if (url.includes("/api/works")) return Promise.resolve(okResponse({ works: [] }));
      if (url.includes("/api/conversations")) {
        return Promise.resolve(okResponse({ conversations: [] }));
      }
      return Promise.resolve(okResponse({}));
    });
  });

  afterEach(() => {
    window.history.replaceState(null, "", "#");
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  /** Mount at the reader route and wait for the first window to paint. */
  async function mountReader(): Promise<void> {
    window.history.replaceState(null, "", READER_HASH);
    render(() => <App />);
    await waitFor(() => {
      expect(document.querySelectorAll(".line").length).toBe(2);
    });
  }

  /** Navigate and let the route settle, so a slow teardown cannot pass a
   *  case by not having finished yet. */
  async function goAndSettle(hash: string): Promise<void> {
    go(hash);
    await waitFor(() => {
      expect(window.location.hash).toBe(hash);
    });
    await Promise.resolve();
    await Promise.resolve();
  }

  it("keeps the same Reader element mounted when the lemma detail opens", async () => {
    await mountReader();
    const before = document.querySelector(".reader");

    await goAndSettle(LEMMA_HASH);

    expect(document.querySelector(".reader")).toBe(before);
  });

  it("keeps the same Reader element mounted when the concordance index opens", async () => {
    // The rail's work-concordance link goes to the index, not the lemma
    // detail — both are step-outs and both have to preserve the Reader.
    await mountReader();
    const before = document.querySelector(".reader");

    await goAndSettle(INDEX_HASH);

    expect(document.querySelector(".reader")).toBe(before);
  });

  it("does not tear down the rendered chunks on the way out or back", async () => {
    await mountReader();
    const firstLine = document.querySelector(".line");

    await goAndSettle(LEMMA_HASH);
    await goAndSettle(READER_HASH);

    // If `loadWork` ran its `setRange(null)` at either step, this is a
    // different object — the whole point of keeping the Reader mounted.
    expect(document.querySelector(".line")).toBe(firstLine);
  });

  it("hides the retained Reader and takes it out of the tab order", async () => {
    // Mounted-but-visible would put the Reader's own content on screen behind
    // the concordance and leave every link in it focusable. `hidden` covers
    // the first, `inert` the second — the same treatment `App` applies to the
    // shell under the syntax layer.
    await mountReader();
    expect(must(keepAlive()).hasAttribute("hidden")).toBe(false);
    expect(must(keepAlive()).hasAttribute("inert")).toBe(false);

    await goAndSettle(LEMMA_HASH);

    expect(must(keepAlive()).hasAttribute("hidden")).toBe(true);
    expect(must(keepAlive()).hasAttribute("inert")).toBe(true);
  });

  it("shows the Reader again when the concordance closes", async () => {
    await mountReader();

    await goAndSettle(LEMMA_HASH);
    await goAndSettle(READER_HASH);

    expect(must(keepAlive()).hasAttribute("hidden")).toBe(false);
    expect(must(keepAlive()).hasAttribute("inert")).toBe(false);
  });

  it("leaves Escape to the concordance instead of exiting the Reader", async () => {
    // `inert` governs focus and pointer events; it does nothing about the
    // window-level `keydown` the Reader's `useEscape` registers. Before this
    // change the Reader was destroyed on the way out, so its listener went
    // with it — retained and un-gated it answered first, and Esc on the
    // concordance fired `onExit` and threw the user out to the landing
    // (measured: the hash went to `#/`).
    //
    // `#/concordance` here is the lemma detail's OWN Esc handler
    // (`LemmaDetail.tsx:98`, back to the index) doing its job, which is the
    // point: the key belongs to whatever is on screen.
    await mountReader();
    await goAndSettle(LEMMA_HASH);

    fireEvent.keyDown(window, { key: "Escape" });
    await Promise.resolve();

    expect(window.location.hash).toBe("#/concordance");
    // Still a step-out route, so the Reader is still being held.
    expect(document.querySelector(".reader")).not.toBeNull();
  });

  it("still renders the concordance itself over the retained Reader", async () => {
    // Keeping the Reader must not cost the route its own content — the
    // `<Switch>` still has to reach the concordance branch.
    await mountReader();

    await goAndSettle(LEMMA_HASH);

    expect(document.querySelector(".conc-stage")).not.toBeNull();
  });
});

describe("the network and refs routes as full-page destinations", () => {
  beforeEach(() => {
    localStorage.clear();
    _resetToastsForTesting();
    invalidateReads();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("occurrence_map") || url.includes("references_map")) {
        return Promise.resolve(okResponse({ work_id: 781, lang: "deu", by_chunk: {} }));
      }
      if (url.includes("/api/works/")) return Promise.resolve(okResponse(RANGE));
      if (url.includes("/api/works")) return Promise.resolve(okResponse({ works: [] }));
      if (url.includes("/api/conversations")) {
        return Promise.resolve(okResponse({ conversations: [] }));
      }
      return Promise.resolve(okResponse({}));
    });
  });

  afterEach(() => {
    window.history.replaceState(null, "", "#");
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  async function mountReader(): Promise<void> {
    window.history.replaceState(null, "", READER_HASH);
    render(() => <App />);
    await waitFor(() => {
      expect(document.querySelectorAll(".line").length).toBe(2);
    });
  }

  async function goAndSettle(hash: string): Promise<void> {
    go(hash);
    await waitFor(() => {
      expect(window.location.hash).toBe(hash);
    });
    await Promise.resolve();
    await Promise.resolve();
  }

  it("releases the Reader for the network dashboard", async () => {
    // Nothing in the Reader links to it — it is reached from the top nav, so
    // there is no passage to come back to and holding one open costs a live
    // window, live effects and a live IntersectionObserver for the session.
    await mountReader();

    await goAndSettle("#/network");

    expect(document.querySelector(".reader")).toBeNull();
    expect(keepAlive()).toBeNull();
  });

  it("releases the Reader for the refs browser", async () => {
    await mountReader();

    await goAndSettle("#/refs");

    expect(document.querySelector(".reader")).toBeNull();
    expect(keepAlive()).toBeNull();
  });

  it("does not resurrect the Reader on a concordance reached after leaving", async () => {
    // Reader → landing drops the retained location. A concordance opened from
    // the top nav afterwards is an entry point, not a step-out, and must not
    // mount a hidden Reader (and refetch its window) behind itself.
    await mountReader();

    await goAndSettle("#/");
    await goAndSettle(LEMMA_HASH);

    expect(document.querySelector(".reader")).toBeNull();
    expect(keepAlive()).toBeNull();
  });

  it("mounts no Reader for a cold load of the concordance", async () => {
    window.history.replaceState(null, "", LEMMA_HASH);
    render(() => <App />);
    await waitFor(() => {
      expect(document.querySelector(".conc-stage")).not.toBeNull();
    });

    expect(keepAlive()).toBeNull();
  });
});
