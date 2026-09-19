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

// Complete on purpose. A partial payload used to crash `Atlas`'s caption
// (`undefined.toLocaleString()`), and because the throw escaped mid-render it
// left the DOM frozen with the composer — and its scope chip — still present.
// A test asserting on the chip then passed over a broken landing.
const LANDING_STATS = { authors: 48, works: 866, xrefs: 54155 };

const KAPITAL_WORK = {
  work_id: 781,
  corpus: "marx",
  author: "Marx",
  work: "Das Kapital, Band I",
  display_title: "Das Kapital, Band I",
  lang: "deu",
  chunks: 1,
};

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

// Slug form since #602. This constant used to read
// `#/r/Das%20Kapital%2C%20Band%20I?lang=deu`.
const READER_HASH = "#/r/das-kapital-band-i?lang=deu";

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

  it("carries the work to the landing as a scope chip (#350)", async () => {
    // `currentWork()` resolves the location against the loaded works list
    // (`readerCtrl.ts:109`), so this test needs `/api/works` to actually
    // return the work — with an empty list there is nothing to seed the
    // scope FROM, and the assertion below would fail for that reason
    // rather than for the behaviour it is testing.
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/syntax")) return Promise.resolve(okResponse(SYNTAX));
      if (url.includes("/api/terms/")) return Promise.resolve(okResponse(TERM));
      if (url.includes("occurrence_map") || url.includes("references_map")) {
        return Promise.resolve(okResponse({ work_id: 781, lang: "deu", by_chunk: {} }));
      }
      if (url.includes("/api/works/")) return Promise.resolve(okResponse(RANGE));
      if (url.includes("/api/works")) {
        return Promise.resolve(
          okResponse({
            works: [
              {
                work_id: 781,
                corpus: "marx",
                author: "Marx",
                work: "Das Kapital, Band I",
                display_title: "Das Kapital, Band I",
                lang: "deu",
                chunks: 1,
              },
            ],
          }),
        );
      }
      if (url.includes("/api/conversations")) {
        return Promise.resolve(okResponse({ conversations: [] }));
      }
      return Promise.resolve(okResponse({}));
    });

    // The half of "Escape leaves the Reader for the landing" that was
    // unbuildable when the Escape gate shipped: the landing composer took
    // no chip and `startFromLanding` cleared the scope, so the work you
    // were reading was dropped on the way out. Escape now seeds the scope
    // the way the back arrow does.
    //
    // Asserted on the rendered chip rather than on `chatScope()`, because
    // the chip being VISIBLE is the whole point — a scope carried silently
    // would be a hidden filter on the next question.
    await mountReader();

    escape();

    await waitFor(() => {
      expect(document.querySelector(".reader")).toBeNull();
    });
    const chip = document.querySelector(".chat-scope");
    expect(chip).not.toBeNull();
    expect(chip?.textContent).toMatch(/Das Kapital, Band I/);
    // And it is dismissible, so the reader is never stuck with it.
    expect(
      document.querySelector('.chat-scope__clear[aria-label^="Clear scope"]'),
    ).not.toBeNull();
  });

  it("lets the landing chip re-scope through its picker (#350)", async () => {
    // The chip is not just a label on the landing — it is the same control
    // as in the conversation composer, so the work can be changed or cleared
    // before the first question. This exercises the `works` / `ensureWorks`
    // wiring `ChatRoute` hands it, which a label-only chip would never call.
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/syntax")) return Promise.resolve(okResponse(SYNTAX));
      if (url.includes("/api/terms/")) return Promise.resolve(okResponse(TERM));
      if (url.includes("occurrence_map") || url.includes("references_map")) {
        return Promise.resolve(okResponse({ work_id: 781, lang: "deu", by_chunk: {} }));
      }
      if (url.includes("/api/works/")) return Promise.resolve(okResponse(RANGE));
      if (url.includes("/api/works")) {
        return Promise.resolve(
          okResponse({
            works: [
              {
                work_id: 781,
                corpus: "marx",
                author: "Marx",
                work: "Das Kapital, Band I",
                display_title: "Das Kapital, Band I",
                lang: "deu",
                chunks: 1,
              },
              {
                work_id: 99,
                corpus: "hegel",
                author: "Hegel",
                work: "Phänomenologie des Geistes",
                display_title: "Phänomenologie des Geistes",
                lang: "deu",
                chunks: 1,
              },
            ],
          }),
        );
      }
      if (url.includes("/api/conversations")) {
        return Promise.resolve(okResponse({ conversations: [] }));
      }
      return Promise.resolve(okResponse({}));
    });

    await mountReader();
    escape();
    await waitFor(() => {
      expect(document.querySelector(".chat-scope")).not.toBeNull();
    });

    const workBtn = document.querySelector<HTMLButtonElement>(".chat-scope__work");
    expect(workBtn).not.toBeNull();
    fireEvent.click(workBtn!);

    // Picker opens and is populated from the works list.
    await waitFor(() => {
      expect(document.querySelector(".chat-scope-pop")).not.toBeNull();
    });
    await waitFor(() => {
      expect(document.querySelectorAll(".chat-scope-pop__list button").length).toBeGreaterThan(0);
    });

    // Clearing drops the chip entirely, so the landing goes back to unscoped.
    fireEvent.click(document.querySelector<HTMLButtonElement>(".chat-scope__clear")!);
    await waitFor(() => {
      expect(document.querySelector(".chat-scope")).toBeNull();
    });
  });

  it("carries the work even when /api/works is still in flight (#428)", async () => {
    // The race #428 was filed on. `currentWork()` reads the lazily-loaded works
    // list while the Reader renders off the route, so leaving inside the
    // `/api/works` round-trip used to seed `null` and drop the work silently.
    //
    // Hold `/api/works` open across the Escape, then release it: the chip must
    // still arrive. Note this cannot be fixed by *retaining* a resolved work —
    // in this state nothing has ever resolved.
    let releaseWorks: (() => void) | undefined;
    const worksGate = new Promise<void>((r) => {
      releaseWorks = r;
    });
    fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/syntax")) return okResponse(SYNTAX);
      if (url.includes("/api/terms/")) return okResponse(TERM);
      if (url.includes("occurrence_map") || url.includes("references_map")) {
        return okResponse({ work_id: 781, lang: "deu", by_chunk: {} });
      }
      if (url.includes("/api/works/")) return okResponse(RANGE);
      if (url.includes("/api/works")) {
        await worksGate;
        return okResponse({ works: [KAPITAL_WORK] });
      }
      if (url.includes("/api/conversations")) return okResponse({ conversations: [] });
      if (url.includes("/api/landing/stats")) return okResponse(LANDING_STATS);
      return okResponse({});
    });

    await mountReader();
    escape();

    // Left the Reader immediately — the exit did not block on the network.
    await waitFor(() => {
      expect(document.querySelector(".reader")).toBeNull();
    });
    // And no chip yet, because the list has not arrived. This is the state that
    // used to be permanent.
    expect(document.querySelector(".chat-scope")).toBeNull();

    releaseWorks!();

    await waitFor(() => {
      expect(document.querySelector(".chat-scope")).not.toBeNull();
    });
    expect(document.querySelector(".chat-scope")?.textContent).toMatch(
      /Das Kapital, Band I/,
    );
  });

  it("does not re-seed a scope the reader cleared while it resolved (#428)", async () => {
    // The late write is only correct while it is still filling the hole it
    // left. Here the reader gets a chip from a warm list, clears it with the
    // ×, and a second exit's late resolution must not put it back — otherwise
    // dismissing the chip would be undone by a race the reader cannot see.
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/syntax")) return Promise.resolve(okResponse(SYNTAX));
      if (url.includes("/api/terms/")) return Promise.resolve(okResponse(TERM));
      if (url.includes("occurrence_map") || url.includes("references_map")) {
        return Promise.resolve(okResponse({ work_id: 781, lang: "deu", by_chunk: {} }));
      }
      if (url.includes("/api/works/")) return Promise.resolve(okResponse(RANGE));
      if (url.includes("/api/works")) {
        return Promise.resolve(okResponse({ works: [KAPITAL_WORK] }));
      }
      if (url.includes("/api/conversations")) {
        return Promise.resolve(okResponse({ conversations: [] }));
      }
      if (url.includes("/api/landing/stats")) return Promise.resolve(okResponse(LANDING_STATS));
      return Promise.resolve(okResponse({}));
    });

    await mountReader();
    escape();
    await waitFor(() => {
      expect(document.querySelector(".chat-scope")).not.toBeNull();
    });

    document.querySelector<HTMLButtonElement>(".chat-scope__clear")!.click();
    await waitFor(() => {
      expect(document.querySelector(".chat-scope")).toBeNull();
    });

    // Nothing may re-seed it afterwards.
    await new Promise((r) => setTimeout(r, 80));
    expect(document.querySelector(".chat-scope")).toBeNull();
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
