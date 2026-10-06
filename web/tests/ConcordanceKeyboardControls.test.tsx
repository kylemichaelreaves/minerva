// #726: the concordance's back, drop-filter, reset, retry and A–Z controls
// were `<a onClick>` with no href, or `<span onClick>` — never focusable, so
// mouse-only. Each is asserted here as a real <button> (focusable, and
// activated by Enter and Space natively) that still does its job when pressed.
// A `role="button"` span would pass a role query and still not be reachable
// without hand-written key handling, so the element type is what's checked.

import { fireEvent, render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type * as concordanceApi from "~/api/concordanceApi";
import type * as readerApi from "~/api/readerApi";
import type { LemmaDetailResponse, LemmaIndexResponse } from "~/api/concordanceApi";

const fetchLemmaIndex = vi.fn<typeof concordanceApi.fetchLemmaIndex>();
const fetchLemmaDetail = vi.fn<typeof concordanceApi.fetchLemmaDetail>();
const listWorks = vi.fn<typeof readerApi.listWorks>();

vi.mock("~/api/readerApi", () => ({
  listWorks: (...args: Parameters<typeof readerApi.listWorks>) => listWorks(...args),
}));

vi.mock("~/api/concordanceApi", async (importOriginal) => {
  const mod = await importOriginal<typeof import("~/api/concordanceApi")>();
  return {
    ...mod,
    fetchLemmaIndex: (...args: Parameters<typeof concordanceApi.fetchLemmaIndex>) =>
      fetchLemmaIndex(...args),
    fetchLemmaDetail: (...args: Parameters<typeof concordanceApi.fetchLemmaDetail>) =>
      fetchLemmaDetail(...args),
  };
});

import { ConcordanceIndexPage, type IndexPageProps } from "~/Concordance/components/IndexPage";
import {
  ConcordanceLemmaDetail,
  type LemmaDetailProps,
} from "~/Concordance/components/LemmaDetail";

function index(overrides: Partial<LemmaIndexResponse> = {}): LemmaIndexResponse {
  return {
    scope: "corpus",
    scope_label: "All German",
    lang: "deu",
    letter: null,
    sort: "freq",
    total_lemmas: 1,
    total_occurrences: 900,
    letter_counts: { A: 1 },
    limit: 200,
    offset: 0,
    next_offset: null,
    rows: [{ rank: 1, lemma: "Abend", pos: "NOUN", count: 900, distinct_works: 1, per_work: [] }],
    ...overrides,
  };
}

function detail(overrides: Partial<LemmaDetailResponse> = {}): LemmaDetailResponse {
  return {
    lemma: "Begriff",
    lang: "deu",
    scope: "author",
    scope_label: "Hegel",
    filters: { pos: null, morph: {}, surface: null },
    total: 0,
    limit: 100,
    offset: 0,
    pos_breakdown: [],
    case_breakdown: [],
    number_breakdown: [],
    gender_breakdown: [],
    surface_breakdown: [],
    work_breakdown: [],
    drop_counts: {},
    rows: [],
    next_offset: null,
    ...overrides,
  };
}

/** The control named `name`, asserted to be a real button. */
async function button(name: string | RegExp): Promise<HTMLButtonElement> {
  const el = await screen.findByRole("button", { name });
  expect(el).toBeInstanceOf(HTMLButtonElement);
  expect((el as HTMLButtonElement).type).toBe("button");
  return el as HTMLButtonElement;
}

function mobile() {
  const desktop = window.matchMedia.bind(window);
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query.includes("max-width: 768px"),
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }));
  return () => {
    window.matchMedia = desktop;
  };
}

beforeEach(() => {
  fetchLemmaIndex.mockReset();
  fetchLemmaDetail.mockReset();
  listWorks.mockReset();
  listWorks.mockResolvedValue([]);
});

describe("<ConcordanceIndexPage /> controls are buttons (#726)", () => {
  function renderIndex(props: Partial<IndexPageProps> = {}) {
    const onNavigate = vi.fn();
    render(() => (
      <ConcordanceIndexPage lang="deu" onNavigate={onNavigate} onOpenLemma={vi.fn()} {...props} />
    ));
    return { onNavigate };
  }

  it("makes every A–Z letter a button", async () => {
    fetchLemmaIndex.mockResolvedValue(index());
    const { onNavigate } = renderIndex();
    fireEvent.click(await button("G"));
    expect(onNavigate).toHaveBeenCalledWith({ letter: "G" });
  });

  it("makes 'all' a button once a letter is chosen", async () => {
    fetchLemmaIndex.mockResolvedValue(index());
    const { onNavigate } = renderIndex({ letter: "A" });
    fireEvent.click(await button("all"));
    expect(onNavigate).toHaveBeenCalledWith({ letter: undefined });
  });

  it.each([
    ["a failed fetch", () => fetchLemmaIndex.mockRejectedValueOnce(new Error("upstream exploded"))],
    [
      "a missing lemma cache",
      () => fetchLemmaIndex.mockRejectedValueOnce(new Error("no lemma cache for deu")),
    ],
    [
      "an empty corpus",
      () =>
        fetchLemmaIndex.mockResolvedValueOnce(
          index({ total_lemmas: 0, total_occurrences: 0, letter_counts: {}, rows: [] }),
        ),
    ],
  ])("makes retry a button after %s, and it refetches", async (_, arrange) => {
    arrange();
    fetchLemmaIndex.mockResolvedValue(index());
    renderIndex();
    fireEvent.click(await button("retry"));
    await waitFor(() => expect(fetchLemmaIndex).toHaveBeenCalledTimes(2));
  });

  describe("mobile filter sheet", () => {
    let restore: () => void;
    beforeEach(() => {
      restore = mobile();
    });
    afterEach(() => restore());

    it("makes Reset all and the done control buttons", async () => {
      fetchLemmaIndex.mockResolvedValue(index());
      const { onNavigate } = renderIndex({ letter: "A", pos: "NOUN" });
      fireEvent.click(await button(/Filters/));
      await button(/lemmas →/);
      fireEvent.click(await button("↺ Reset all"));
      expect(onNavigate).toHaveBeenCalled();
    });
  });
});

describe("<ConcordanceLemmaDetail /> controls are buttons (#726)", () => {
  function renderDetail(props: Partial<LemmaDetailProps> = {}) {
    const onNavigate = vi.fn();
    const onBackToIndex = vi.fn();
    render(() => (
      <ConcordanceLemmaDetail
        lemma="Begriff"
        lang="deu"
        scope="author"
        scopeAuthors={["Hegel"]}
        onNavigate={onNavigate}
        onBackToIndex={onBackToIndex}
        onOpenChunk={vi.fn()}
        {...props}
      />
    ));
    return { onNavigate, onBackToIndex };
  }

  it("makes 'back to index' a button", async () => {
    fetchLemmaDetail.mockResolvedValue(detail());
    const { onBackToIndex } = renderDetail();
    fireEvent.click(await button("‹ back to index"));
    expect(onBackToIndex).toHaveBeenCalled();
  });

  it("makes the empty state's Drop Surface form and Zoom to corpus buttons", async () => {
    fetchLemmaDetail.mockResolvedValue(detail());
    const { onNavigate } = renderDetail({ surface: "Begriffe" });
    fireEvent.click(await button("Drop Surface form"));
    expect(onNavigate).toHaveBeenCalledWith({ surface: undefined });
    fireEvent.click(await button("Zoom to corpus"));
    expect(onNavigate).toHaveBeenCalledWith({ scope: "corpus" });
  });

  describe("mobile filter sheet", () => {
    let restore: () => void;
    beforeEach(() => {
      restore = mobile();
    });
    afterEach(() => restore());

    it("makes Reset all and the done control buttons", async () => {
      fetchLemmaDetail.mockResolvedValue(detail({ total: 3 }));
      const { onNavigate } = renderDetail({ surface: "Begriffe" });
      fireEvent.click(await button(/Filters/));
      await button(/occurrences →/);
      fireEvent.click(await button("↺ Reset all"));
      expect(onNavigate).toHaveBeenCalled();
    });
  });
});
