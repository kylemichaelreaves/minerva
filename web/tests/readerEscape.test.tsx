import { fireEvent, render, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi, type MockedFunction } from "vitest";
import App from "~/App";
import { invalidateReads } from "~/api/readCache";
import { _resetToastsForTesting } from "~/utils/apiError";
import { okResponse } from "./helpers/testRouting";

// Escape leaves the Reader — but only when nothing else is using it.
//
// Every transient surface in the Reader already answers Escape: the translate
// rail, the term and xref cards, the selection toolbar, the mobile settings
// sheet, and — since #342 made it a layer over a Reader that stays mounted —
// the syntax overlay. So "Esc exits" has to be the LAST thing Escape means,
// not the first, or dismissing a card would also throw the reader away.
//
// The unit half of this lives in `readerUtils.test.ts`, which names all six
// surfaces. These are the wiring: that the gate is fed the real state, and
// that a surface with its own listener wins the keypress.

const RANGE = {
  work_id: 781,
  corpus: "marx",
  author: "Marx",
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
      text: "Die Ware ist zunächst ein äußerer Gegenstand.",
      ord: 0,
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

// Shaped as `TermDetail` in `src/api/types/reader.ts` — every field is
// required there, and `TermCard` reads `renderings` without a guard, so a
// partial fixture crashes the card rather than rendering an empty one.
const TERM = {
  id: 42,
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

const READER_HASH = "#/r/Das%20Kapital%2C%20Band%20I?lang=deu";

let fetchMock: MockedFunction<typeof fetch>;

const escape = (): void => {
  fireEvent.keyDown(window, { key: "Escape" });
};

describe("Escape in the Reader", () => {
  beforeEach(() => {
    localStorage.clear();
    _resetToastsForTesting();
    invalidateReads();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/syntax")) return Promise.resolve(okResponse(SYNTAX));
      if (url.includes("/api/terms/")) return Promise.resolve(okResponse(TERM));
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

  /** Mount at `hash` and wait for the Reader's first window to paint. */
  async function mountReader(hash: string = READER_HASH): Promise<void> {
    window.history.replaceState(null, "", hash);
    render(() => <App />);
    await waitFor(() => {
      expect(document.querySelectorAll(".line").length).toBe(1);
    });
  }

  it("leaves for the landing when nothing else is open", async () => {
    await mountReader();

    escape();

    await waitFor(() => {
      expect(document.querySelector(".reader")).toBeNull();
    });
    expect(window.location.hash).toBe("#/");
  });

  it("closes the term card instead of leaving", async () => {
    await mountReader(`${READER_HASH}&term=42`);
    await waitFor(() => {
      expect(document.querySelector(".termcard")).not.toBeNull();
    });

    escape();

    await waitFor(() => {
      expect(document.querySelector(".termcard")).toBeNull();
    });
    expect(document.querySelector(".reader")).not.toBeNull();
    expect(window.location.hash).toBe(READER_HASH);
  });

  it("leaves on the press after the term card is closed", async () => {
    await mountReader(`${READER_HASH}&term=42`);
    await waitFor(() => {
      expect(document.querySelector(".termcard")).not.toBeNull();
    });
    escape();
    await waitFor(() => {
      expect(document.querySelector(".termcard")).toBeNull();
    });

    escape();

    await waitFor(() => {
      expect(document.querySelector(".reader")).toBeNull();
    });
    expect(window.location.hash).toBe("#/");
  });

  it("closes the syntax layer instead of leaving", async () => {
    // The interaction #342 created: the Reader is mounted UNDER the overlay
    // now, so its Escape listener is live while the overlay owns the key.
    await mountReader(`${READER_HASH}&syntax=k-1`);
    await waitFor(() => {
      expect(document.querySelector(".syn")).not.toBeNull();
    });

    escape();

    await waitFor(() => {
      expect(document.querySelector(".syn")).toBeNull();
    });
    expect(document.querySelector(".reader")).not.toBeNull();
    expect(window.location.hash).toBe(READER_HASH);
  });

  it("does not fire outside the Reader", async () => {
    // The listener belongs to the Reader, so a landing-route Escape must not
    // navigate anywhere — there is nothing to escape from.
    window.history.replaceState(null, "", "#/");
    render(() => <App />);
    await waitFor(() => {
      expect(document.querySelector(".app")).not.toBeNull();
    });

    escape();

    expect(window.location.hash).toBe("#/");
  });
});
