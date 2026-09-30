import { afterEach, beforeEach, describe, expect, it, vi, type MockedFunction } from "vitest";
import { render, waitFor } from "@solidjs/testing-library";
import type { JSX } from "solid-js";
import App from "~/App";
import Reader from "~/Reader";
import { invalidateReads } from "~/api/readCache";
import { MobileShellProvider } from "~/components/shell/MobileShellContext";
import { _resetToastsForTesting } from "~/utils/apiError";

/** The route carries slugs; the TITLE arrives with the data (#602).
 *
 *  Four things read the work title out of the Reader, and the route no longer
 *  carries one. The saved-highlight localStorage key is the one with a real
 *  migration attached — it is keyed on the title string, and every existing
 *  user's annotation layer is filed under it. Sourcing the title from the
 *  range response instead of the route is what makes that migration
 *  unnecessary, and this is the test that says so. */

let fetchMock: MockedFunction<typeof fetch>;

function okResponse(body: unknown): Response {
  return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
}

const RANGE = {
  work_id: 999,
  corpus: "plato",
  author: "Plato",
  work: "Republic",
  lang: "grc",
  total: 1,
  offset: 0,
  limit: 200,
  chunks: [
    {
      chunk_id: "r-1",
      section: "509d",
      book: "6",
      page: null,
      speaker: null,
      text: "τοῦ πατρός",
      ord: 0,
    },
  ],
};

function renderReader(ui: () => JSX.Element) {
  return render(() => <MobileShellProvider>{ui()}</MobileShellProvider>);
}

describe("the saved-highlight key stays title-based", () => {
  beforeEach(() => {
    localStorage.clear();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/works/")) return Promise.resolve(okResponse(RANGE));
      return Promise.resolve(okResponse({}));
    });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("paints a highlight stored under the TITLE while the route carries the SLUG", async () => {
    localStorage.setItem(
      "minerva:highlights:Republic",
      JSON.stringify([{ chunkId: "r-1", start: 0, end: 3, source: "τοῦ", ref: "509d" }]),
    );
    const { container } = renderReader(() => <Reader workSlug="republic" sourceLang="grc" />);
    await waitFor(() => expect(container.querySelector(".pin-hl.saved")).not.toBeNull());
  });

  it("does not read the annotation layer out of a key named after the slug", async () => {
    // The failure this rules out is silent: keying on `republic` would find
    // nothing, the Reader would render fine, and the user's highlights would
    // simply be gone.
    localStorage.setItem(
      "minerva:highlights:republic",
      JSON.stringify([{ chunkId: "r-1", start: 0, end: 3, source: "τοῦ", ref: "509d" }]),
    );
    const { container } = renderReader(() => <Reader workSlug="republic" sourceLang="grc" />);
    await waitFor(() => expect(container.querySelector(".gw")).not.toBeNull());
    expect(container.querySelector(".pin-hl.saved")).toBeNull();
  });
});

/** A one-segment citation link grows its author segment once the range names
 *  the author (#611), and growing it is not a change of window.
 *
 *  `authorSlug` is one of the fields `useWorkRange`'s window memo is keyed on
 *  (#347), so a naive `replace()` re-keyed the window: `loadWork` ran its
 *  `setRange(null)` and the stage blanked and refetched. The fetch count is a
 *  sound witness here where it is not in readerSyntaxLayer: the grown route
 *  asks for `/api/works/plato/republic`, a different cache key from
 *  `/api/works/republic`, so a reload cannot be served out of the read cache
 *  without touching `fetch`. Node identity backs it up. */
describe("a one-segment reader URL", () => {
  const urlOf = (input: RequestInfo | URL): string =>
    typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  const rangeUrls = (): string[] =>
    fetchMock.mock.calls
      .map(([input]) => urlOf(input))
      .filter((u) => /\/api\/works\/[^?]*republic/.test(u));

  beforeEach(() => {
    localStorage.clear();
    _resetToastsForTesting();
    invalidateReads();
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.includes("occurrence_map") || url.includes("references_map")) {
        return Promise.resolve(okResponse({ work_id: 999, lang: "grc", by_chunk: {} }));
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

  it("grows to #/r/<authorSlug>/<titleSlug> in place once the range names the author", async () => {
    window.history.replaceState(null, "", "#/r/republic?lang=grc&focus=r-1");
    const historyLength = window.history.length;
    render(() => <App />);

    await waitFor(() => expect(window.location.hash).toBe("#/r/plato/republic?lang=grc&focus=r-1"));
    // `replace`, not `push`: the back button must not step through the
    // one-segment form.
    expect(window.history.length).toBe(historyLength);

    const line = document.querySelector(".line");
    expect(line).not.toBeNull();
    // Let any reload the grown route triggered run to completion.
    await new Promise((r) => setTimeout(r, 20));
    expect(document.querySelector(".line")).toBe(line);
    expect(rangeUrls()).toEqual(["/api/works/republic?lang=grc&limit=200&around=r-1"]);
  });

  it("does not pair the range's author with a title slug the range is not", async () => {
    // A focus link resolves off `around=` whatever the title segment says, so
    // the range can be a different work from the one the slug names. Growing
    // that into `plato/politeia` would build a URL that resolves nothing.
    window.history.replaceState(null, "", "#/r/politeia?lang=grc&focus=r-1");
    render(() => <App />);
    await waitFor(() => expect(document.querySelector(".line")).not.toBeNull());
    await new Promise((r) => setTimeout(r, 20));
    expect(window.location.hash).toBe("#/r/politeia?lang=grc&focus=r-1");
  });

  it("leaves a two-segment URL alone", async () => {
    window.history.replaceState(null, "", "#/r/plato/republic?lang=grc");
    render(() => <App />);
    await waitFor(() => expect(document.querySelector(".line")).not.toBeNull());
    expect(window.location.hash).toBe("#/r/plato/republic?lang=grc");
    expect(rangeUrls()).toHaveLength(1);
  });
});
