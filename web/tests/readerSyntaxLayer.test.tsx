import { render, waitFor } from "@solidjs/testing-library";
import { fireEvent } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi, type MockedFunction } from "vitest";
import App from "~/App";
import { invalidateReads } from "~/api/readCache";
import { SyntaxLayer } from "~/routes/SyntaxLayer";
import { _resetToastsForTesting } from "~/utils/apiError";
import { createTestRouting, okResponse } from "./helpers/testRouting";
import { must } from "./helpers/must";

// The syntax overlay is a LAYER over the Reader, not a peer route (#342).
//
// It was wired as a sibling `<Match>` of the same `<Switch>`, so opening it
// unmounted the Reader: `useWorkRange`'s signals were destroyed, the window
// refetched, and the return trip landed on a blank page that then scrolled
// itself back with the deep-link animation. The response cache from #343 made
// that fast; it could not make it stop happening.
//
// These assertions are deliberately NOT fetch counts. A cached read serves the
// refetch without touching `fetch`, so a count would pass while the Reader was
// still being torn down and rebuilt. Node identity cannot be faked: if the
// Reader unmounts, or if `loadWork` runs its `setRange(null)`, the elements are
// different objects afterwards.

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

const SYNTAX = {
  chunk_id: "k-1",
  sentences: [
    {
      sent_ord: 0,
      tokens: [
        {
          id: 1,
          form: "Ware",
          lemma: "Ware",
          upos: "NOUN",
          xpos: "NN",
          feats: null,
          misc: null,
          head: 0,
          deprel: "root",
          start: 4,
          end: 8,
          corrected: false,
        },
      ],
    },
  ],
  corrections: [],
};

// Slug form since #602. This constant used to read
// `#/r/Das%20Kapital%2C%20Band%20I?lang=deu`.
const READER_HASH = "#/r/das-kapital-band-i?lang=deu";
const SYNTAX_OPEN_HASH = `${READER_HASH}&syntax=k-1`;

let fetchMock: MockedFunction<typeof fetch>;

/** Drive the hash the way the browser's back/forward buttons do — the app
 *  reads the URL on popstate and never writes history from an effect. */
function go(hash: string): void {
  window.history.pushState(null, "", hash);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

describe("the syntax overlay as a layer over the Reader", () => {
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
      if (url.includes("/syntax")) return Promise.resolve(okResponse(SYNTAX));
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

  it("keeps the same Reader element mounted when the overlay opens", async () => {
    await mountReader();
    const before = document.querySelector(".reader");

    go(SYNTAX_OPEN_HASH);
    await waitFor(() => {
      expect(document.querySelector(".syn")).not.toBeNull();
    });

    expect(document.querySelector(".reader")).toBe(before);
  });

  it("does not tear down the rendered chunks when the overlay opens", async () => {
    await mountReader();
    const firstLine = document.querySelector(".line");

    go(SYNTAX_OPEN_HASH);
    await waitFor(() => {
      expect(document.querySelector(".syn")).not.toBeNull();
    });
    // Give a reload one more turn to land, so a slow `loadWork` cannot pass
    // this by having not finished blanking the stage yet.
    await Promise.resolve();

    expect(document.querySelector(".line")).toBe(firstLine);
  });

  it("keeps the Reader mounted for the legacy #/syntax/<chunk>?work= hash too", async () => {
    // The shape #237 shipped, and the one any existing bookmark holds. It has
    // to keep working, and it has to stop unmounting the Reader — this is the
    // exact navigation that made the page blank.
    await mountReader();
    const before = document.querySelector(".reader");

    go("#/syntax/k-1?work=Das%20Kapital%2C%20Band%20I");
    await waitFor(() => {
      expect(document.querySelector(".syn")).not.toBeNull();
    });

    expect(document.querySelector(".reader")).toBe(before);
  });

  it("marks the shell inert while the overlay is over it", async () => {
    // The Reader staying mounted is the point, but a mounted Reader under an
    // opaque `position: fixed` layer is still in the tab order — it was
    // unreachable before only because it was destroyed. `inert` on the shell
    // is what replaces that.
    await mountReader();
    const shell = must(document.querySelector("main.main"));
    expect(shell.hasAttribute("inert")).toBe(false);

    go(SYNTAX_OPEN_HASH);
    await waitFor(() => {
      expect(document.querySelector(".syn")).not.toBeNull();
    });
    expect(shell.hasAttribute("inert")).toBe(true);

    go(READER_HASH);
    await waitFor(() => {
      expect(document.querySelector(".syn")).toBeNull();
    });
    expect(shell.hasAttribute("inert")).toBe(false);
  });

  it("returns to the reader route without a focus jump when the overlay closes", async () => {
    window.history.replaceState(null, "", SYNTAX_OPEN_HASH);
    render(() => <App />);
    await waitFor(() => {
      expect(document.querySelector(".syn")).not.toBeNull();
    });
    const reader = document.querySelector(".reader");

    fireEvent.click(must(document.querySelector(".syn-back")));

    await waitFor(() => {
      expect(document.querySelector(".syn")).toBeNull();
    });
    // No `focus=` on the way back: the Reader never left, so there is nothing
    // to scroll to and the `.focused` deep-link animation must not fire.
    expect(window.location.hash).toBe(READER_HASH);
    expect(document.querySelector(".reader")).toBe(reader);
  });

  it("does not navigate on close when the route has already left the reader", async () => {
    // The layer's close handler rebuilds the route it is a modifier ON, so it
    // has nothing to say once that route is gone — a sidebar click or a back
    // button between paint and click would otherwise navigate to a reader
    // route synthesised out of a landing one.
    const routing = createTestRouting({ kind: "landing" });
    render(() => <SyntaxLayer routing={routing} chunkId="k-1" />);
    await waitFor(() => {
      expect(document.querySelector(".syn")).not.toBeNull();
    });

    fireEvent.click(must(document.querySelector(".syn-back")));

    expect(routing.navigateSpy).not.toHaveBeenCalled();
  });
});
