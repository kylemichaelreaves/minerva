// What the concordance index says when a response comes back with no rows.
//
// Two different empties: a language whose lemma cache has never been built
// (every total is zero, no letter, corpus scope) gets the "run the
// lemmatizer" explainer; anything narrower — a letter, a scope, or a cache
// that has totals but nothing matching — is just "No lemmas in this scope".
// Mistaking one for the other would tell a reader to run a batch job over a
// perfectly healthy index.

import { fireEvent, render, screen } from "@solidjs/testing-library";
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

import { ConcordanceIndexPage, type IndexPageProps } from "~/Concordance/components/IndexPage";

function empty(overrides: Record<string, unknown> = {}) {
  return {
    scope: "corpus",
    scope_label: "All German",
    lang: "deu",
    letter: null,
    sort: "freq",
    total_lemmas: 0,
    total_occurrences: 0,
    letter_counts: {},
    limit: 200,
    offset: 0,
    next_offset: null,
    rows: [],
    ...overrides,
  };
}

function renderIndex(props: Partial<IndexPageProps> = {}) {
  return render(() => (
    <ConcordanceIndexPage lang="deu" onNavigate={vi.fn()} onOpenLemma={vi.fn()} {...props} />
  ));
}

beforeEach(() => {
  fetchLemmaIndex.mockReset();
  listWorks.mockReset();
  listWorks.mockResolvedValue([]);
});

describe("<ConcordanceIndexPage /> — empty responses", () => {
  it("explains a missing lemma cache when every total is zero", async () => {
    fetchLemmaIndex.mockResolvedValue(empty());
    renderIndex();

    expect(await screen.findByText("No lemma cache for DEU")).toBeInTheDocument();
    expect(screen.queryByText("No lemmas in this scope")).toBeNull();
  });

  it("re-fetches when the missing-cache retry link is clicked", async () => {
    fetchLemmaIndex.mockResolvedValue(empty());
    renderIndex();
    await screen.findByText("No lemma cache for DEU");
    const before = fetchLemmaIndex.mock.calls.length;

    fireEvent.click(screen.getByText("retry"));

    await vi.waitFor(() => {
      expect(fetchLemmaIndex.mock.calls.length).toBeGreaterThan(before);
    });
  });

  it.each([
    ["the cache has lemmas", { total_lemmas: 12 }, {}],
    ["the cache has occurrences", { total_occurrences: 40 }, {}],
    ["a letter is selected", {}, { letter: "Q" }],
    ["the scope is narrowed", {}, { scope: "author" as const, scopeAuthors: ["Kant"] }],
  ])("says 'No lemmas in this scope' when %s", async (_label, response, props) => {
    fetchLemmaIndex.mockResolvedValue(empty(response));
    renderIndex(props);

    expect(await screen.findByText("No lemmas in this scope")).toBeInTheDocument();
    expect(screen.queryByText(/No lemma cache/)).toBeNull();
  });
});
