// The lemma-detail surfaces a reader reaches with filters applied: the
// empty-results "broaden" links, and the mobile filter button + sheet.
//
// The broaden links quote how many hits dropping a filter would bring back.
// The server counts that (`drop_counts`, #691); the client used to rebuild it
// from the facet breakdowns, which describe the unfiltered scope and only the
// tokens carrying the feature, and so undercounted every uncased lemma.
// Clicking one must clear exactly that filter and leave the others alone.

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type * as concordanceApi from "~/api/concordanceApi";
import type { LemmaDetailResponse } from "~/api/concordanceApi";
import { render, screen } from "@solidjs/testing-library";

const fetchLemmaDetail = vi.fn<typeof concordanceApi.fetchLemmaDetail>();

vi.mock("~/api/concordanceApi", async (importOriginal) => {
  const mod = await importOriginal<typeof import("~/api/concordanceApi")>();
  return {
    ...mod,
    fetchLemmaDetail: (...args: Parameters<typeof concordanceApi.fetchLemmaDetail>) =>
      fetchLemmaDetail(...args),
  };
});

import {
  ConcordanceLemmaDetail,
  type LemmaDetailProps,
} from "~/Concordance/components/LemmaDetail";
import { must } from "./helpers/must";
import { fireEvent } from "./helpers/settledFireEvent";

const ROW = {
  chunk_id: "c-1",
  section: "¶1",
  book: "I",
  work: "Kritik der reinen Vernunft",
  author: "Kant",
  ord: 0,
  surface: "Begriffe",
  pos: "NOUN",
  morph: {},
  morph_str: "",
  kwic_left: "der ",
  kwic_match: "Begriffe",
  kwic_right: " ist",
};

function detail(overrides: Partial<LemmaDetailResponse> = {}): LemmaDetailResponse {
  return {
    lemma: "Begriff",
    lang: "deu",
    scope: "corpus" as const,
    scope_label: "the corpus",
    filters: { pos: null, morph: {}, surface: null },
    total: 0,
    limit: 100,
    offset: 0,
    pos_breakdown: [],
    case_breakdown: [
      { value: "Nom", count: 1200 },
      { value: "Gen", count: 34 },
    ],
    number_breakdown: [
      { value: "Sing", count: 900 },
      { value: "Plur", count: 5 },
    ],
    gender_breakdown: [],
    surface_breakdown: [],
    work_breakdown: [],
    drop_counts: {},
    rows: [],
    next_offset: null,
    ...overrides,
  };
}

function renderDetail(props: Partial<LemmaDetailProps> = {}) {
  const onNavigate = vi.fn();
  const utils = render(() => (
    <ConcordanceLemmaDetail
      lemma="Begriff"
      lang="deu"
      scope="corpus"
      onNavigate={onNavigate}
      onBackToIndex={vi.fn()}
      onOpenChunk={vi.fn()}
      {...props}
    />
  ));
  return { onNavigate, ...utils };
}

/** The morph filter the component asked the server for. */
function requestedMorph(): unknown {
  return must(fetchLemmaDetail.mock.calls[0], "a fetchLemmaDetail call")[0].morph;
}

beforeEach(() => {
  fetchLemmaDetail.mockReset();
});

describe("<ConcordanceLemmaDetail /> — empty results with filters", () => {
  it("quotes the server's per-filter drop counts when both Case and Number are set", async () => {
    // Deliberately unlike the facet buckets (Gen 34, Plur 5): with a surface
    // filter active the facets say nothing about what a drop returns.
    fetchLemmaDetail.mockResolvedValue(detail({ drop_counts: { Number: 7, Case: 3 } }));
    const { onNavigate } = renderDetail({ caseFilter: "Gen", numberFilter: "Plur" });

    const dropNumber = await screen.findByText("Drop Number · 7 hits");
    const dropCase = screen.getByText("Drop Case · 3 hits");

    expect(screen.getByText("No occurrences with these filters")).toBeInTheDocument();
    expect(requestedMorph()).toEqual({ Case: "Gen", Number: "Plur" });

    fireEvent.click(dropNumber);
    expect(onNavigate).toHaveBeenLastCalledWith({ numberFilter: undefined });
    fireEvent.click(dropCase);
    expect(onNavigate).toHaveBeenLastCalledWith({ caseFilter: undefined });
  });

  it("renders each drop control as a keyboard-reachable button (#726)", async () => {
    fetchLemmaDetail.mockResolvedValue(detail({ drop_counts: { Number: 7, Case: 3 } }));
    renderDetail({ caseFilter: "Gen", numberFilter: "Plur" });

    const dropNumber = await screen.findByRole("button", { name: "Drop Number · 7 hits" });
    expect(dropNumber).toHaveAttribute("type", "button");
    expect(screen.getByRole("button", { name: "Drop Case · 3 hits" })).toBeInTheDocument();
  });

  it("quotes the server's count for Drop Number, not the case facet's sum (#691)", async () => {
    // A verb: its case facet holds only the participles, so the facet's sum
    // (1,234 here) is far below what dropping Number returns.
    fetchLemmaDetail.mockResolvedValue(detail({ drop_counts: { Number: 72738 } }));
    renderDetail({ numberFilter: "Dual" });

    expect(await screen.findByText(`Drop Number · ${(72738).toLocaleString()} hits`)).toBeTruthy();
    expect(screen.queryByText(/Drop Case/)).toBeNull();
    expect(requestedMorph()).toEqual({ Number: "Dual" });
  });

  it("quotes the server's count for Drop Case", async () => {
    fetchLemmaDetail.mockResolvedValue(detail({ drop_counts: { Case: 1896 } }));
    const { onNavigate } = renderDetail({ caseFilter: "Voc" });

    const link = await screen.findByText(`Drop Case · ${(1896).toLocaleString()} hits`);
    expect(screen.queryByText(/Drop Number/)).toBeNull();
    expect(requestedMorph()).toEqual({ Case: "Voc" });

    fireEvent.click(link);
    expect(onNavigate).toHaveBeenCalledWith({ caseFilter: undefined });
  });

  it("omits the hit count when the server sent none for that filter", async () => {
    fetchLemmaDetail.mockResolvedValue(detail());
    renderDetail({ caseFilter: "Dat", numberFilter: "Dual" });

    // The link must not print "undefined hits".
    expect(await screen.findByText("Drop Number")).toBeInTheDocument();
    expect(screen.getByText("Drop Case")).toBeInTheDocument();
  });
});

describe("<ConcordanceLemmaDetail /> — mobile filter sheet", () => {
  const desktopMatchMedia = window.matchMedia.bind(window);
  beforeEach(() => {
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
  });
  afterEach(() => {
    window.matchMedia = desktopMatchMedia;
  });

  it("badges the filter button with the active-filter count and opens the sheet", async () => {
    fetchLemmaDetail.mockResolvedValue(detail({ total: 1234, rows: [ROW] }));
    const { onNavigate } = renderDetail({
      caseFilter: "Nom",
      numberFilter: "Sing",
      surface: "Begriffe",
    });

    const fab = await screen.findByRole("button", { name: /Filters/ });
    expect(must(fab.querySelector(".badge")).textContent).toBe("3");
    // The sheet is closed until the button is pressed.
    expect(screen.queryByText("↺ Reset all")).toBeNull();

    fireEvent.click(fab);

    const done = must(document.querySelector(".conc-mob-sheet-foot .done"), "the sheet footer");
    expect(done.textContent).toBe(`${(1234).toLocaleString()} occurrences →`);

    fireEvent.click(screen.getByText("↺ Reset all"));
    expect(onNavigate).toHaveBeenCalledWith({
      caseFilter: undefined,
      numberFilter: undefined,
      surface: undefined,
    });
    // Reset also closes the sheet.
    expect(screen.queryByText("↺ Reset all")).toBeNull();
  });

  it("shows no badge when no filter is active", async () => {
    fetchLemmaDetail.mockResolvedValue(detail({ total: 1, rows: [ROW] }));
    renderDetail();

    const fab = await screen.findByRole("button", { name: /Filters/ });
    expect(fab.querySelector(".badge")).toBeNull();
  });
});
