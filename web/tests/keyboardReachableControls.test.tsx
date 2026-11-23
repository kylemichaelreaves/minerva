// Controls that were reachable by mouse only (#773).
//
// Each was an intrinsic element carrying `onClick` with no role, no tabindex
// and no key handler: not in the tab order, and inert to Enter or Space. The
// assertions are by role, the way assistive technology finds a control, so any
// implementation that passes is one a keyboard can reach and operate. HTML
// buttons get Enter/Space activation from the browser, so for those the role
// and a click are the whole contract; the SVG and table-row controls cannot be
// buttons, so their key handling is asserted directly.
//
// Not covered, deliberately: four sites with a keyboard path elsewhere or a
// click that only dismisses (KwicRow, ArcPanel's arcs, NetworkArc's backdrop
// and its tooltip), and WordRun, which needs a design of its own. Each carries
// an eslint-disable naming its reason; eslint.mouseOnly.js is the gate.

import { fireEvent, render, screen, waitFor, within } from "@solidjs/testing-library";
import { flush } from "solid-js";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LemmaDetailResponse } from "~/api/concordanceApi";
import { fetchNetworkSummary, type AuthorPair } from "~/api/networkApi";
import { ActiveFilterStrip } from "~/Concordance/components/ActiveFilterStrip";
import { FilterBar } from "~/Concordance/components/FilterBar";
import { FilterRail } from "~/Concordance/components/FilterRail";
import { ScopePill } from "~/Concordance/components/ScopePill";
import { ATLAS_AUTHORS } from "~/data/atlasData";
import { Atlas } from "~/Network/components/Atlas";
import { RequestLedger } from "~/Metrics/RequestLedger";
import { NetworkArc } from "~/Network/components/NetworkArc";
import { ConcordanceTabPanel } from "~/Reader/components/ConcordanceTabPanel";
import { must } from "./helpers/must";
import { makeNetworkSummary } from "./helpers/networkSummary";

vi.mock("~/api/networkApi", async (importOriginal) => ({
  ...(await importOriginal<typeof import("~/api/networkApi")>()),
  fetchNetworkSummary: vi.fn(),
}));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Concordance filter chips", () => {
  it("ActiveFilterStrip: each pill's remove and 'reset all' are buttons", () => {
    const onRemove = vi.fn();
    const onReset = vi.fn();
    render(() => (
      <ActiveFilterStrip items={[{ k: "POS", v: "noun", onRemove }]} onReset={onReset} />
    ));
    fireEvent.click(screen.getByRole("button", { name: "Remove POS: noun" }));
    expect(onRemove).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: /reset all/ }));
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("FilterBar: a scoped author's and a scoped work's remove are buttons", () => {
    const onPickAuthor = vi.fn();
    const onPickWork = vi.fn();
    const props = {
      lang: "deu" as const,
      sort: "freq" as const,
      freqCeil: 1000,
      authorOptions: [],
      workOptions: [],
      onSetLang: vi.fn(),
      onSetSort: vi.fn(),
      onSetPos: vi.fn(),
      onSetFreqRange: vi.fn(),
      onSetQ: vi.fn(),
      onPickAuthor,
      onPickWork,
    };
    const { unmount } = render(() => (
      <FilterBar {...props} scope="author" scopeAuthors={["Kant"]} />
    ));
    fireEvent.click(screen.getByRole("button", { name: "Remove Kant from the scope" }));
    expect(onPickAuthor).toHaveBeenCalledWith("Kant");
    unmount();

    render(() => <FilterBar {...props} scope="work" scopeWorks={["Ethik"]} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove Ethik from the scope" }));
    expect(onPickWork).toHaveBeenCalledWith("Ethik");
  });

  it("ScopePill: every step but the current one is a button", () => {
    const onPick = vi.fn();
    render(() => (
      <ScopePill
        steps={[
          { label: "Corpus", scope: "corpus", cur: false },
          { label: "Kant", scope: "author", cur: true },
        ]}
        onPick={onPick}
      />
    ));
    fireEvent.click(screen.getByRole("button", { name: "Corpus" }));
    expect(onPick).toHaveBeenCalledWith("corpus");
    expect(screen.queryByRole("button", { name: "Kant" })).toBeNull();
  });
});

describe("Concordance filter rail", () => {
  const bucket = (value: string, count: number) => ({ value, count });
  const DATA: LemmaDetailResponse = {
    lemma: "virtus",
    lang: "lat",
    scope: "corpus",
    scope_label: "Corpus",
    filters: { pos: null, morph: {}, surface: null },
    total: 0,
    limit: 50,
    offset: 0,
    pos_breakdown: [],
    case_breakdown: [],
    number_breakdown: [],
    gender_breakdown: [],
    // One past each cap (WORK_CAP 8, SURFACE_CAP 6), so both expanders show.
    surface_breakdown: Array.from({ length: 7 }, (_, i) => bucket(`form${String(i)}`, 7 - i)),
    work_breakdown: Array.from({ length: 9 }, (_, i) => bucket(`Work ${String(i)}`, 9 - i)),
    drop_counts: {},
    rows: [],
    next_offset: null,
  };

  function renderRail() {
    const handlers = {
      onSetScope: vi.fn(),
      onSetCase: vi.fn(),
      onSetNumber: vi.fn(),
      onSetSurface: vi.fn(),
      onToggleWork: vi.fn(),
      onClearWorks: vi.fn(),
      onResetAll: vi.fn(),
    };
    render(() => (
      <FilterRail
        data={DATA}
        scope="author"
        scopeAuthors={["Cicero"]}
        scopeWorks={["Work 0"]}
        surface="form1"
        {...handlers}
      />
    ));
    return handlers;
  }

  it("the scope segments are buttons that say which one is on", () => {
    const h = renderRail();
    const bar = within(must(document.querySelector<HTMLElement>(".fr-scope")));
    const corpus = bar.getByRole("button", { name: "Corpus" });
    expect(corpus).toHaveAttribute("aria-pressed", "false");
    expect(bar.getByRole("button", { name: "Cicero" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(corpus);
    expect(h.onSetScope).toHaveBeenCalledWith(expect.objectContaining({ scope: "corpus" }));
    fireEvent.click(bar.getByRole("button", { name: "Work 0" }));
    expect(h.onSetScope).toHaveBeenCalledWith({ scope: "work" });
  });

  it("the applied card's reset and pill remove are buttons", () => {
    const h = renderRail();
    fireEvent.click(screen.getByRole("button", { name: "Remove surface: form1" }));
    expect(h.onSetSurface).toHaveBeenCalledWith(undefined);
    fireEvent.click(screen.getByRole("button", { name: /↺ reset/ }));
    expect(h.onResetAll).toHaveBeenCalledTimes(1);
  });

  it("each work in the list is a toggle button", () => {
    const h = renderRail();
    // The scope bar's Work segment is also named for the sole selected work.
    const check = (name: RegExp) =>
      must(screen.getAllByRole("button", { name }).find((b) => b.classList.contains("fr-check")));
    const first = check(/Work 0/);
    expect(first).toHaveAttribute("aria-pressed", "true");
    expect(check(/Work 1/)).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(first);
    expect(h.onToggleWork).toHaveBeenCalledWith("Work 0");
  });

  it("both '+N more' expanders are buttons", () => {
    renderRail();
    fireEvent.click(screen.getByRole("button", { name: /1 more work\b/ }));
    flush();
    expect(screen.getByRole("button", { name: /Work 8/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /1 more form\b/ }));
    flush();
    expect(screen.getByRole("button", { name: "form6" })).toBeInTheDocument();
  });
});

describe("Reader concordance tab", () => {
  it("each lemma row is a button that opens the lemma", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            rows: [{ lemma: "λόγος", pos: "NOUN", count: 52, distinct_works: 1, per_work: [] }],
            total_lemmas: 1,
            total_tokens: 52,
            letter_counts: {},
          }),
      }),
    );
    const onOpenLemma = vi.fn();
    render(() => (
      <ConcordanceTabPanel
        workTitle="Categories"
        lang="grc"
        onOpenWorkScope={vi.fn()}
        onOpenLemma={onOpenLemma}
      />
    ));
    const row = await screen.findByRole("button", { name: /λόγος/ });
    fireEvent.click(row);
    expect(onOpenLemma).toHaveBeenCalledWith("λόγος");
  });
});

describe("Metrics request ledger", () => {
  it("a row is focusable and Enter or Space selects it", async () => {
    const row = {
      id: "a1b2c3d4e5f60718",
      at: 1_700_000_000,
      label: "chat",
      method: "POST",
      status: 200,
      total_ms: 5400,
      accounted_ms: 4812,
      unaccounted_ms: 588,
      phases: [{ name: "llm_call", ms: 4812 }],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            window: "24h",
            since: 0,
            until: 1,
            rows: [row, { ...row, id: "f" }],
            limit: 200,
          }),
      }),
    );
    render(() => <RequestLedger window="24h" />);
    await screen.findAllByText("chat");
    const [first, second] = [
      ...document.querySelectorAll<HTMLTableRowElement>(".mledger-table tbody tr"),
    ];
    const tr = must(first);
    expect(tr.tabIndex).toBe(0);
    tr.focus();
    expect(document.activeElement).toBe(tr);
    fireEvent.keyDown(tr, { key: "Enter" });
    await waitFor(() => {
      expect(tr).toHaveAttribute("aria-selected", "true");
    });
    fireEvent.keyDown(must(second), { key: " " });
    await waitFor(() => {
      expect(must(second)).toHaveAttribute("aria-selected", "true");
    });
  });
});

describe("SVG author and arc controls", () => {
  it("Atlas: an author is a focusable button that Enter and Space pick", () => {
    const onPickAuthor = vi.fn();
    render(() => <Atlas onPickAuthor={onPickAuthor} stats={null} isMobile={() => false} />);
    const name = must(ATLAS_AUTHORS[0]).name;
    const author = screen.getByRole("button", { name: `${name}: open references` });
    expect(author).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(author, { key: "Enter" });
    fireEvent.keyDown(author, { key: " " });
    fireEvent.keyDown(author, { key: "a" });
    expect(onPickAuthor).toHaveBeenCalledTimes(2);
    expect(onPickAuthor).toHaveBeenCalledWith(name);
  });

  it("Atlas: focusing an author shows the card hovering does, and blur hides it", () => {
    const { container } = render(() => (
      <Atlas onPickAuthor={vi.fn()} stats={null} isMobile={() => false} />
    ));
    const name = must(ATLAS_AUTHORS[0]).name;
    const author = screen.getByRole("button", { name: `${name}: open references` });
    expect(container.querySelector(".atlas-tooltip")).toBeNull();
    fireEvent.focus(author);
    flush();
    expect(must(container.querySelector(".atlas-tooltip")).textContent).toContain(name);
    fireEvent.blur(author);
    flush();
    expect(container.querySelector(".atlas-tooltip")).toBeNull();
  });

  it("NetworkArc: an author and an arc are focusable buttons", async () => {
    const pair = (src: string, tgt: string, n: number): AuthorPair => ({
      src,
      tgt,
      n,
      intra_scrip: false,
    });
    vi.mocked(fetchNetworkSummary).mockResolvedValueOnce(
      makeNetworkSummary({ xrefs: 90, pairs: [pair("Nietzsche", "Plato", 90)] }),
    );
    const onOpenAuthor = vi.fn();
    const { container } = render(() => <NetworkArc onBack={vi.fn()} onOpenAuthor={onOpenAuthor} />);

    const author = await screen.findByRole("button", { name: "Plato: open author" });
    expect(author).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(author, { key: "Enter" });
    expect(onOpenAuthor).toHaveBeenCalledWith("Plato");

    const arc = screen.getByRole("button", { name: "Nietzsche → Plato: 90 references" });
    expect(arc).toHaveAttribute("tabindex", "0");
    expect(container.querySelector(".net-tooltip")).toBeNull();
    fireEvent.keyDown(arc, { key: "Enter" });
    flush();
    expect(must(container.querySelector(".net-tooltip .pair")).textContent).toBe("Nietzsche→Plato");
  });
});
