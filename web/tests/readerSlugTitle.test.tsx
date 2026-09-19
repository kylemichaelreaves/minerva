import { afterEach, beforeEach, describe, expect, it, vi, type MockedFunction } from "vitest";
import { render, waitFor } from "@solidjs/testing-library";
import type { JSX } from "solid-js";
import Reader from "~/Reader";
import { MobileShellProvider } from "~/components/shell/MobileShellContext";

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
