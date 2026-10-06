import { fireEvent, render, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi, type MockedFunction } from "vitest";
import App from "~/App";
import { invalidateReads } from "~/api/readCache";
import { _resetToastsForTesting } from "~/utils/apiError";
import { makeLemmaDetail, makeLemmaIndex } from "./helpers/concordance";
import { okResponse } from "./helpers/testRouting";

// A retained Reader keeps global listeners armed that `inert` cannot reach (#352).
//
// #348 hoisted the Reader out of the `<Switch>` so a step-out to the concordance
// no longer destroys it. That made "mounted but not on screen" a normal state for
// the first time, and `inert` governs focus and pointer events — not listeners
// bound to `window` or `document`. #348 threaded a `suspended` flag to the two
// whose misfire it measured (the Reader's own Escape, the selection toolbar's
// hotkeys); the term card's binds the rest.
//
// The two cases below are the ones that destroy user state — the open term card
// is exactly what #348 exists to preserve, and both a click and an Escape on the
// concordance dismiss it AND clear `?term=` from the URL.
//
// On the Escape case specifically: there is no precedence to win. `useEscape`
// calls `preventDefault()` and NOT `stopPropagation()`, and every handler is a
// bubble-phase `window` listener, so one Escape runs both the card's dismissal
// and the concordance's own navigation. Asserting only that the concordance
// navigates passes today while the card is still being destroyed.
//
// Worse, so does asserting the card is merely *present*. Measured on this
// branch before the fix: Escape destroys the card, and the concordance's own
// navigation then changes the route, which re-runs `useTermCard`'s URL-resume
// effect (`?term=` is still 7 — `setOpenTermId` early-returns off the reader
// route, so `close()` never cleared it) and rebuilds the card at the SENTINEL
// anchor, viewport top. Presence: true. Same node: false. The user's anchor,
// the card's fetch and its focus state are all gone.
//
// So the Escape case asserts NODE IDENTITY, the same way `readerKeepAlive`
// asserts it for the Reader itself and for the same reason.

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

const TERM = {
  id: 7,
  source_form: "Ware",
  source_language: "deu",
  transliteration: null,
  lemma: "Ware",
  short_gloss: "commodity",
  long_description: "The elementary form of capitalist wealth.",
  renderings: [],
  occurrences_by_edition: [],
  related: [],
};

/** A reader route with a term card already open, resumed from `?term=`. */
const READER_TERM_HASH = "#/r/Das%20Kapital%2C%20Band%20I?lang=deu&term=7";
const LEMMA_HASH = "#/concordance/Ware";

let fetchMock: MockedFunction<typeof fetch>;

function go(hash: string): void {
  window.history.pushState(null, "", hash);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

describe("a suspended Reader stops answering global events", () => {
  beforeEach(() => {
    localStorage.clear();
    _resetToastsForTesting();
    invalidateReads();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/terms/")) return Promise.resolve(okResponse(TERM));
      // The concordance this file steps out to. Unmocked, both fell through to
      // `{}` and the surface crashed into its error boundary (#761).
      if (url.includes("/api/concordance/lemma")) {
        return Promise.resolve(okResponse(makeLemmaDetail()));
      }
      if (url.includes("/api/concordance/index")) {
        return Promise.resolve(okResponse(makeLemmaIndex()));
      }
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

  /** Mount at the reader route with `?term=7`, and wait for both the window
   *  and the resumed term card to paint. */
  async function mountReaderWithCard(): Promise<void> {
    window.history.replaceState(null, "", READER_TERM_HASH);
    render(() => <App />);
    await waitFor(() => {
      expect(document.querySelectorAll(".line").length).toBe(2);
    });
    await waitFor(() => {
      expect(document.querySelector(".termcard")).not.toBeNull();
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

  it("keeps the retained term card when a click lands on the concordance", async () => {
    await mountReaderWithCard();
    await goAndSettle(LEMMA_HASH);

    // The concordance is not inside `.termcard`, so `useClickOutside`'s
    // document-level mousedown treats every click on it as "outside".
    fireEvent.mouseDown(document.body);
    await Promise.resolve();

    expect(document.querySelector(".termcard")).not.toBeNull();
  });

  it("keeps the SAME term card node when Escape is pressed on the concordance", async () => {
    await mountReaderWithCard();
    await goAndSettle(LEMMA_HASH);
    const before = document.querySelector(".termcard");

    fireEvent.keyDown(window, { key: "Escape" });
    await Promise.resolve();

    // Not `not.toBeNull()` — a destroyed-and-rebuilt card satisfies that while
    // having lost its anchor, its fetch and its focus. See the header note.
    expect(document.querySelector(".termcard")).toBe(before);
  });

  it("does not trap Tab inside the retained term card", async () => {
    // `useDialogFocus` binds a document-level `keydown` and, while active,
    // calls `preventDefault()` on Tab to cycle focus within the dialog
    // (`useDialogFocus.tsx:29-44`). Retained, its root is inside a
    // `display: none` subtree, so the elements it hands focus to cannot take
    // it — Tab on the concordance is cancelled and goes nowhere.
    await mountReaderWithCard();
    await goAndSettle(LEMMA_HASH);

    // Shift+Tab is the branch that bites: its guard is `current === first ||
    // !root.contains(current)`, and focus while stepped out is on the
    // concordance, i.e. never inside the retained card — so the second
    // disjunct is always true and every shift-Tab on the concordance is
    // cancelled and redirected into a card nobody can see.
    const tab = new KeyboardEvent("keydown", {
      key: "Tab",
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    });
    document.dispatchEvent(tab);
    await Promise.resolve();

    expect(tab.defaultPrevented).toBe(false);
  });

  it("still lets the concordance handle its own Escape with a card retained", async () => {
    // The gate must silence the Reader's subtree without costing the route on
    // screen its own key handling — `LemmaDetail`'s Escape goes back to the index.
    await mountReaderWithCard();
    await goAndSettle(LEMMA_HASH);

    fireEvent.keyDown(window, { key: "Escape" });
    await Promise.resolve();

    expect(window.location.hash).toBe("#/concordance");
  });
});
