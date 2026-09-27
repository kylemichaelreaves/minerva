// Paging the concordance index (#371).
//
// The list was hard-capped at 200 rows with no way past it, while the header
// printed the true total beside it — 135,047 lemmas for German, measured. The
// cursor comes from the server (`next_offset`) rather than from `total_lemmas`,
// which is not a row count: it ignores the frequency range, and on one branch
// counts DISTINCT lemma while rows are per (lemma, pos).

import { render, waitFor } from "@solidjs/testing-library";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchLemmaIndex = vi.fn();
const listWorks = vi.fn();

vi.mock("~/api/readerApi", () => ({
  listWorks: (...args: unknown[]) => listWorks(...args) as never,
}));

vi.mock("~/api/concordanceApi", async (importOriginal) => {
  const mod = await importOriginal<typeof import("~/api/concordanceApi")>();
  return {
    ...mod,
    fetchLemmaIndex: (...args: unknown[]) => fetchLemmaIndex(...args) as never,
  };
});

import { ConcordanceIndexPage } from "~/Concordance/components/IndexPage";
import { must } from "./helpers/must";

const PAGE = 200;

/** `n` rows whose lemmas are distinct, so appended pages are distinguishable. */
function makeRows(from: number, n: number) {
  return Array.from({ length: n }, (_, i) => ({
    rank: from + i + 1,
    lemma: `lemma${from + i}`,
    pos: "NOUN",
    count: 1000 - (from + i),
    distinct_works: 2,
    per_work: [
      { work: "A", n: 600 },
      { work: "B", n: 400 },
    ],
  }));
}

function page(offset: number, n: number, nextOffset: number | null) {
  return {
    scope: "corpus",
    scope_label: "All German",
    lang: "deu",
    letter: null,
    sort: "freq",
    total_lemmas: 135047,
    total_occurrences: 9_000_000,
    limit: PAGE,
    offset,
    next_offset: nextOffset,
    rows: makeRows(offset, n),
  };
}

/** Captures the observer callback so a test can say "the sentinel came into
 *  view". `setup.ts`'s stub is a no-op, so without this the sentinel can never
 *  fire and none of this is reachable. */
let fireIntersect: (() => void) | null = null;
const realIO = globalThis.IntersectionObserver;

beforeEach(() => {
  fetchLemmaIndex.mockReset();
  listWorks.mockReset();
  listWorks.mockResolvedValue([]);
  fireIntersect = null;
  globalThis.IntersectionObserver = class {
    constructor(cb: IntersectionObserverCallback) {
      fireIntersect = () => {
        cb(
          [{ isIntersecting: true } as IntersectionObserverEntry],
          this as unknown as IntersectionObserver,
        );
      };
    }
    observe() {
      /* no-op */
    }
    unobserve() {
      /* no-op */
    }
    disconnect() {
      /* no-op */
    }
  } as unknown as typeof IntersectionObserver;
});

afterEach(() => {
  globalThis.IntersectionObserver = realIO;
});

const mount = () =>
  render(() => (
    <ConcordanceIndexPage lang="deu" scope="corpus" onNavigate={vi.fn()} onOpenLemma={vi.fn()} />
  ));

const rowCount = (c: HTMLElement) => c.querySelectorAll(".lb-row").length;

describe("concordance index paging", () => {
  it("appends the next page at the offset the server handed back", async () => {
    fetchLemmaIndex
      .mockResolvedValueOnce(page(0, PAGE, PAGE))
      .mockResolvedValueOnce(page(PAGE, 50, null));

    const { container } = mount();
    await waitFor(() => expect(rowCount(container)).toBe(PAGE));

    must(fireIntersect)();

    await waitFor(() => expect(rowCount(container)).toBe(PAGE + 50));
    const second = must(fetchLemmaIndex.mock.calls[1])[0] as Record<string, unknown>;
    expect(second.offset).toBe(PAGE);
    expect(second.limit).toBe(PAGE);
  });

  it("stops asking once next_offset is null", async () => {
    // The whole point of a server cursor: `total_lemmas` says 135,047, so a
    // length-vs-total test would keep requesting pages forever.
    fetchLemmaIndex.mockResolvedValueOnce(page(0, 50, null));

    const { container } = mount();
    await waitFor(() => expect(rowCount(container)).toBe(50));

    expect(fireIntersect).toBeNull();
    expect(fetchLemmaIndex).toHaveBeenCalledTimes(1);
  });

  it("does not stack requests when the sentinel fires twice in flight", async () => {
    // The re-entrancy guard. A sentinel can intersect repeatedly while a page
    // is still loading, and each extra call would append the SAME offset again
    // — duplicating rows rather than advancing.
    let release: ((v: unknown) => void) | null = null;
    fetchLemmaIndex
      .mockResolvedValueOnce(page(0, PAGE, PAGE))
      .mockReturnValueOnce(new Promise((r) => (release = r)));

    const { container } = mount();
    await waitFor(() => expect(rowCount(container)).toBe(PAGE));

    must(fireIntersect)();
    must(fireIntersect)();
    must(fireIntersect)();

    // One page in flight, not three.
    expect(fetchLemmaIndex).toHaveBeenCalledTimes(2);

    must<(v: unknown) => void>(release)(page(PAGE, 50, null));
    await waitFor(() => expect(rowCount(container)).toBe(PAGE + 50));
    expect(fetchLemmaIndex).toHaveBeenCalledTimes(2);
  });

  it("counts the appended rows, not just the first page", async () => {
    // `ActiveFilterStrip` showed `data().rows.length`, which would freeze at
    // 200 while the list grew underneath it. The strip only renders when a
    // filter is active, hence the letter.
    fetchLemmaIndex
      .mockResolvedValueOnce(page(0, PAGE, PAGE))
      .mockResolvedValueOnce(page(PAGE, 50, null));

    const { container } = render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="corpus"
        letter="L"
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));
    await waitFor(() => expect(rowCount(container)).toBe(PAGE));
    must(fireIntersect)();
    await waitFor(() => expect(rowCount(container)).toBe(PAGE + 50));

    expect(container.querySelector(".afs-ct")?.textContent).toContain("250");
  });

  it("keeps the header's scope total, which is a different number", async () => {
    // The header deliberately reports the unfiltered scope total for
    // orientation. It is not the row count and must not be confused for one.
    fetchLemmaIndex.mockResolvedValueOnce(page(0, PAGE, PAGE));

    const { container } = mount();
    await waitFor(() => expect(rowCount(container)).toBe(PAGE));

    expect(container.textContent).toContain("135,047");
  });
});
