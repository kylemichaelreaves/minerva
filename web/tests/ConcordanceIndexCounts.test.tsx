// The two numbers the concordance index shows a reader, and what they count.
//
// #376 — the A–Z rail marked a letter as having hits only when one of its
// lemmas appeared in the rows already fetched. On the default freq-sorted
// corpus view that is whatever reached the top of the sort, so a letter with
// thousands of lemmas rendered as empty. Measured on the live index, German
// corpus scope: G holds 11,125 lemmas and S holds 15,366, and neither was
// visible on first paint. The counts now come from the server, computed over
// the whole filtered scope.
//
// #377 — `total_lemmas` sat immediately beside the row list, in the position a
// reader takes for "how many rows are in this list". It is not that number: it
// ignores the frequency range, whose default `min_count` is 2, so the default
// view already diverged — 28,963 printed above 11,413 rows, measured. The
// header now shows both, always.

import { render, screen, waitFor } from "@solidjs/testing-library";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

/** One row, lemma "Abend" — initial A, and A alone among the fetched rows. */
const ROWS = [
  {
    rank: 1,
    lemma: "Abend",
    pos: "NOUN",
    count: 900,
    distinct_works: 2,
    per_work: [
      { work: "A", n: 600 },
      { work: "B", n: 300 },
    ],
  },
];

function response(overrides: Record<string, unknown> = {}) {
  return {
    scope: "corpus",
    scope_label: "All German",
    lang: "deu",
    letter: null,
    sort: "freq",
    total_lemmas: 135047,
    total_occurrences: 9_000_000,
    // G and S are populous in scope and absent from `rows` — the exact case
    // the client-side fold got wrong.
    letter_counts: { A: 4, G: 11125, S: 15366, Z: 1 },
    limit: 200,
    offset: 0,
    next_offset: null,
    rows: ROWS,
    ...overrides,
  };
}

function railLetter(L: string): HTMLElement | undefined {
  return Array.from(document.querySelectorAll(".az-rail .l")).find(
    (el) => el.textContent === L,
  ) as HTMLElement | undefined;
}

beforeEach(() => {
  fetchLemmaIndex.mockReset();
  fetchLemmaIndex.mockResolvedValue(response());
  listWorks.mockReset();
  listWorks.mockResolvedValue([]);
});

describe("A–Z rail populations (#376)", () => {
  it("marks a populous letter even when no fetched row starts with it", async () => {
    render(() => (
      <ConcordanceIndexPage lang="deu" onNavigate={vi.fn()} onOpenLemma={vi.fn()} />
    ));
    // Wait for the response, not merely for the rail to exist — the rail
    // renders before the fetch resolves.
    await waitFor(() => expect(railLetter("G")!.className).toContain("has"));

    // Only "Abend" was fetched, so folding the rows would light A and nothing
    // else. G and S are in scope and must be lit too.
    expect(railLetter("S")!.className).toContain("has");
    expect(railLetter("A")!.className).toContain("has");
  });

  it("leaves a letter with nothing in scope unmarked", async () => {
    render(() => (
      <ConcordanceIndexPage lang="deu" onNavigate={vi.fn()} onOpenLemma={vi.fn()} />
    ));
    await waitFor(() => expect(railLetter("A")!.className).toContain("has"));

    expect(railLetter("Q")!.className).not.toContain("has");
  });

  it("names the population in the letter's tooltip", async () => {
    // The dot says "something here"; the count says how much, which is what
    // makes the rail worth reading before clicking.
    render(() => (
      <ConcordanceIndexPage lang="deu" onNavigate={vi.fn()} onOpenLemma={vi.fn()} />
    ));
    await waitFor(() =>
      expect(railLetter("S")!.getAttribute("title")).toContain("15,366"),
    );
  });

  it("says 'lemma' for a letter holding exactly one", async () => {
    render(() => (
      <ConcordanceIndexPage lang="deu" onNavigate={vi.fn()} onOpenLemma={vi.fn()} />
    ));
    await waitFor(() =>
      expect(railLetter("Z")!.getAttribute("title")).toBe("Z — 1 lemma"),
    );
  });

  it("does not fall back to folding the fetched rows when the scope is empty", async () => {
    // A response with no letters in scope must render an empty rail, not one
    // derived from whatever rows happen to be present.
    fetchLemmaIndex.mockResolvedValue(response({ letter_counts: {} }));
    render(() => (
      <ConcordanceIndexPage lang="deu" onNavigate={vi.fn()} onOpenLemma={vi.fn()} />
    ));
    await waitFor(() => expect(fetchLemmaIndex).toHaveBeenCalled());
    await waitFor(() =>
      expect(railLetter("A")!.getAttribute("title")).toContain("nothing in scope"),
    );
    expect(railLetter("A")!.className).not.toContain("has");
  });
});

describe("header counts (#377)", () => {
  it("shows the loaded row count beside the scope total", async () => {
    render(() => (
      <ConcordanceIndexPage lang="deu" onNavigate={vi.fn()} onOpenLemma={vi.fn()} />
    ));

    // One row loaded, 135,047 lemmas in scope. Both present, and the scope
    // total labelled as a scope figure rather than as the list's size.
    expect(await screen.findByText("135,047")).toBeInTheDocument();
    expect(screen.getByText(/in scope/)).toBeInTheDocument();
    const head = document.querySelector(".conc-sub")!;
    expect(head.textContent).toContain("Showing 1");
  });

  it("tracks the loaded count as pages append", async () => {
    fetchLemmaIndex.mockResolvedValueOnce(
      response({
        rows: [...ROWS, { ...ROWS[0]!, rank: 2, lemma: "Bild" }],
        next_offset: null,
      }),
    );
    render(() => (
      <ConcordanceIndexPage lang="deu" onNavigate={vi.fn()} onOpenLemma={vi.fn()} />
    ));

    await waitFor(() =>
      expect(document.querySelector(".conc-sub")!.textContent).toContain("Showing 2"),
    );
  });
});
