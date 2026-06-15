// Work/author scope narrowing on the concordance index page: an
// incomplete scope (scope=work without a work) must render a picker
// prompt and never hit the lemma-index endpoint (the backend 400s on
// scope=work without ?work=).

import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@solidjs/testing-library";

const fetchLemmaIndex = vi.fn();

vi.mock("~/api/readerApi", () => ({
  listWorks: vi.fn(() => Promise.resolve([
    {
      work_id: 1,
      corpus: "kant",
      author: "Kant",
      work: "Kritik der reinen Vernunft",
      display_title: "Kritik der reinen Vernunft",
      lang: "deu",
      chunks: 1560,
    },
    {
      work_id: 2,
      corpus: "hegel",
      author: "Hegel",
      work: "Phänomenologie des Geistes",
      display_title: "Phänomenologie des Geistes",
      lang: "deu",
      chunks: 808,
    },
    {
      work_id: 3,
      corpus: "plato",
      author: "Plato",
      work: "Republic",
      display_title: "Republic",
      lang: "grc",
      chunks: 500,
    },
  ])),
}));

vi.mock("~/api/concordanceApi", async (importOriginal) => {
  const mod = await importOriginal<typeof import("~/api/concordanceApi")>();
  return {
    ...mod,
    fetchLemmaIndex: (...args: unknown[]) => fetchLemmaIndex(...args) as never,
  };
});

import { ConcordanceIndexPage } from "~/Concordance/components/IndexPage";

const emptyIndex = {
  scope: "work",
  scope_label: "Kritik der reinen Vernunft",
  lang: "deu",
  letter: null,
  sort: "freq",
  total_lemmas: 1,
  total_occurrences: 1313,
  limit: 200,
  offset: 0,
  rows: [
    {
      lemma: "Begriff",
      pos: "NOUN",
      count: 1313,
      distinct_works: 1,
      per_work: [],
    },
  ],
};

beforeEach(() => {
  fetchLemmaIndex.mockReset();
  fetchLemmaIndex.mockResolvedValue(emptyIndex);
});

describe("ConcordanceIndexPage scope narrowing", () => {
  it("renders a picker prompt and skips the fetch when scope=work has no work", async () => {
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="work"
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));
    expect(await screen.findByText("Choose a work")).toBeInTheDocument();
    expect(fetchLemmaIndex).not.toHaveBeenCalled();
  });

  it("renders a picker prompt and skips the fetch when scope=author has no author", async () => {
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="author"
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));
    expect(await screen.findByText("Choose an author")).toBeInTheDocument();
    expect(fetchLemmaIndex).not.toHaveBeenCalled();
  });

  it("fetches with the work param once a work is selected", async () => {
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="work"
        scopeWorks={["Kritik der reinen Vernunft"]}
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));
    await waitFor(() => expect(fetchLemmaIndex).toHaveBeenCalled());
    const args = fetchLemmaIndex.mock.calls[0]![0] as Record<string, unknown>;
    expect(args.scope).toBe("work");
    expect(args.works).toEqual(["Kritik der reinen Vernunft"]);
    expect(await screen.findByText("Begriff")).toBeInTheDocument();
  });

  it("fetches with both works selected, tab-joined into the work param", async () => {
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="work"
        scopeWorks={["Kritik der reinen Vernunft", "Phänomenologie des Geistes"]}
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));
    await waitFor(() => expect(fetchLemmaIndex).toHaveBeenCalled());
    const args = fetchLemmaIndex.mock.calls[0]![0] as Record<string, unknown>;
    expect(args.scope).toBe("work");
    expect(args.works).toEqual([
      "Kritik der reinen Vernunft",
      "Phänomenologie des Geistes",
    ]);
  });

  it("shows an active-filter chip per selected work", async () => {
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="work"
        scopeWorks={["Kritik der reinen Vernunft", "Phänomenologie des Geistes"]}
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));
    // Each title surfaces in two places — the active-filter strip chip
    // and the desktop FilterBar's selected-work chip — so both titles
    // are present at least once.
    expect((await screen.findAllByText("Kritik der reinen Vernunft")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Phänomenologie des Geistes")).length).toBeGreaterThan(0);
  });

  it("renders the picker prompt and skips the fetch when scope=work has an empty works array", async () => {
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="work"
        scopeWorks={[]}
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));
    expect(await screen.findByText("Choose a work")).toBeInTheDocument();
    expect(fetchLemmaIndex).not.toHaveBeenCalled();
  });

  it("fetches with the author param once an author is selected", async () => {
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="author"
        scopeAuthors={["Kant"]}
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));
    await waitFor(() => expect(fetchLemmaIndex).toHaveBeenCalled());
    const args = fetchLemmaIndex.mock.calls[0]![0] as Record<string, unknown>;
    expect(args.scope).toBe("author");
    expect(args.authors).toEqual(["Kant"]);
  });

  it("fetches with both authors selected (sent tab-joined into the author param)", async () => {
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="author"
        scopeAuthors={["Kant", "Hegel"]}
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));
    await waitFor(() => expect(fetchLemmaIndex).toHaveBeenCalled());
    const args = fetchLemmaIndex.mock.calls[0]![0] as Record<string, unknown>;
    expect(args.scope).toBe("author");
    expect(args.authors).toEqual(["Kant", "Hegel"]);
  });

  it("shows an active-filter chip per selected author", async () => {
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="author"
        scopeAuthors={["Kant", "Hegel"]}
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));
    // Each author surfaces in two places — the active-filter strip chip
    // and the desktop FilterBar's selected-author chip — so both names
    // are present at least once.
    expect((await screen.findAllByText("Kant")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText("Hegel")).length).toBeGreaterThan(0);
  });

  it("renders the picker prompt and skips the fetch when scope=author has an empty authors array", async () => {
    render(() => (
      <ConcordanceIndexPage
        lang="deu"
        scope="author"
        scopeAuthors={[]}
        onNavigate={vi.fn()}
        onOpenLemma={vi.fn()}
      />
    ));
    expect(await screen.findByText("Choose an author")).toBeInTheDocument();
    expect(fetchLemmaIndex).not.toHaveBeenCalled();
  });
});
