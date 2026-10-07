// Tests for `<Refs>` — the corpus-wide cross-references browser.
// Covers the filter-fetch-render cycle that the maintainability audit
// flagged as having no test coverage.

import { describe, it, expect, beforeEach, afterEach, vi, type MockedFunction } from "vitest";
import { render, fireEvent, waitFor } from "@solidjs/testing-library";
import Refs, { type RefsProps } from "~/features/Refs";
import { MobileShellProvider } from "~/components/shell/MobileShellContext";
import type { ReferencesListResponse, ReferencesListRow } from "~/api/refsApi";
import { must } from "./helpers/must";

let fetchMock: MockedFunction<typeof fetch>;

function renderRefs(props: RefsProps) {
  return render(() => (
    <MobileShellProvider>
      <Refs {...props} />
    </MobileShellProvider>
  ));
}

function okResponse(body: unknown): Response {
  return { ok: true, json: () => Promise.resolve(body) } as unknown as Response;
}

function makeRow(overrides: Partial<ReferencesListRow> = {}): ReferencesListRow {
  return {
    id: 1,
    source_chunk_id: "rep-509d",
    source_span_start: null,
    source_span_end: null,
    source_form: "Aristoteles",
    quoted_phrase: null,
    target: {
      author: "Aristotle",
      work: "Nicomachean Ethics",
      in_corpus_work_id: 42,
      chunk_id: "ne-1097b",
      locator: "1097b",
      locator_payload: null,
      sort_key: null,
    },
    reference_type: "cites",
    confidence: 0.9,
    source_method: "rule+embed+llm",
    curator_status: "approved",
    curated_by: null,
    curated_at: null,
    note: null,
    source: {
      author: "Plato",
      work: "Republic",
      section: "509d",
    },
    ...overrides,
  };
}

function makeResponse(
  rows: ReferencesListRow[],
  overrides: Partial<ReferencesListResponse> = {},
): ReferencesListResponse {
  return {
    limit: 50,
    offset: 0,
    total: rows.length,
    filters: {
      source_author: null,
      target_author: null,
      target_work: null,
      reference_type: null,
    },
    references: rows,
    ...overrides,
  };
}

function defaultProps(overrides: Partial<RefsProps> = {}): RefsProps {
  return {
    onNavigate: vi.fn(),
    onOpenSource: vi.fn(),
    ...overrides,
  };
}

describe("<Refs />", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("fetches on mount and renders one card per row", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse(
        makeResponse([
          makeRow(),
          makeRow({
            id: 2,
            source_chunk_id: "rep-510a",
            source: { author: "Plato", work: "Republic", section: "510a" },
          }),
        ]),
      ),
    );
    const props = defaultProps();
    const { container } = renderRefs(props);
    await waitFor(() => {
      expect(container.querySelectorAll(".ref-row").length).toBe(2);
    });
    // Summary shows total count.
    expect(container.querySelector(".refs-meta")?.textContent).toContain("2 references");
    // First row shows source author + work + locator and the chip.
    const firstRow = container.querySelector(".ref-row");
    expect(firstRow?.textContent).toContain("Plato");
    expect(firstRow?.textContent).toContain("Republic");
    expect(firstRow?.textContent).toContain("509d");
    expect(firstRow?.textContent).toContain("Aristotle");
    expect(firstRow?.querySelector(".ref-row-chip")?.textContent).toBe("cites");
  });

  it("forwards filter props to the API request", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(makeResponse([])));
    const props = defaultProps({
      sourceAuthor: "Aquinas",
      targetAuthor: "Aristotle",
      referenceType: "quotes",
      includeRejected: true,
    });
    renderRefs(props);
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });
    const url = must(fetchMock.mock.calls[0])[0] as string;
    expect(url).toContain("source_author=Aquinas");
    expect(url).toContain("target_author=Aristotle");
    expect(url).toContain("reference_type=quotes");
    expect(url).toContain("include_rejected=1");
  });

  it("includeRejected toggle pushes onNavigate", async () => {
    fetchMock.mockResolvedValue(okResponse(makeResponse([makeRow()])));
    const props = defaultProps({ includeRejected: false });
    const { container } = renderRefs(props);
    await waitFor(() => {
      expect(container.querySelector(".ref-row")).not.toBeNull();
    });
    const checkbox = must(container.querySelector(".refs-filter-check input[type=checkbox]"));
    expect(checkbox).not.toBeNull();
    fireEvent.click(checkbox);
    expect(props.onNavigate).toHaveBeenCalledWith(
      expect.objectContaining({ includeRejected: true }),
    );
  });

  it("clicking a row calls onOpenSource with (workTitle, chunkId)", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(makeResponse([makeRow()])));
    const props = defaultProps();
    const { container } = renderRefs(props);
    await waitFor(() => {
      expect(container.querySelector(".ref-row")).not.toBeNull();
    });
    fireEvent.click(must(container.querySelector(".ref-row")));
    expect(props.onOpenSource).toHaveBeenCalledWith("Republic", "rep-509d");
  });

  it("empty result with active filters shows EmptyState + 'Clear filters'", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(makeResponse([])));
    const props = defaultProps({ sourceAuthor: "Aquinas" });
    const { container } = renderRefs(props);
    await waitFor(() => {
      expect(container.querySelector(".refs-empty")).not.toBeNull();
    });
    const clearBtn = must(container.querySelector(".refs-clear"));
    expect(clearBtn).not.toBeNull();
    fireEvent.click(clearBtn);
    // Clearing pushes onNavigate with every filter cleared.
    expect(props.onNavigate).toHaveBeenCalledWith({
      sourceAuthor: undefined,
      targetAuthor: undefined,
      targetWork: undefined,
      referenceType: undefined,
      includeRejected: false,
    });
  });

  it("failed fetch renders an error block (no rows)", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: "Server Error",
    } as Response);
    const props = defaultProps();
    const { container } = renderRefs(props);
    await waitFor(() => {
      expect(container.querySelector(".refs-error")).not.toBeNull();
    });
    expect(container.querySelectorAll(".ref-row").length).toBe(0);
  });

  it("renders 'Review queue →' affordance when onOpenReview is wired", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(makeResponse([])));
    const onOpenReview = vi.fn();
    const props = defaultProps({ onOpenReview });
    const { container } = renderRefs(props);
    await waitFor(() => {
      expect(container.querySelector(".refs-review-link")).not.toBeNull();
    });
    fireEvent.click(must(container.querySelector(".refs-review-link")));
    expect(onOpenReview).toHaveBeenCalled();
  });

  // A reference row opens its source passage. Until #324's batch it was a
  // bare `<li onClick>` — no name, no tab stop, no key handling — so a mouse
  // was the only way to reach it (typescript:S6847, typescript:S1082). The
  // click path is already covered above; these cover what it lacked.
  async function renderOneRow() {
    fetchMock.mockResolvedValueOnce(okResponse(makeResponse([makeRow()])));
    const props = defaultProps();
    const { container } = renderRefs(props);
    await waitFor(() => {
      expect(container.querySelector(".ref-row")).not.toBeNull();
    });
    return { props, row: must(container.querySelector<HTMLElement>(".ref-row")) };
  }

  it("gives a reference row a tab stop", async () => {
    const { row } = await renderOneRow();
    row.focus();
    expect(document.activeElement).toBe(row);
  });

  it("makes a reference row a native button", async () => {
    // Asserted as an element type rather than by simulating Enter, because
    // Enter- and Space-to-activate is the platform's behaviour for a
    // <button> and jsdom does not implement it — a `fireEvent.keyDown` test
    // here would pass only against a hand-rolled key handler, i.e. it would
    // pin the workaround instead of the fix. A native button is also what
    // typescript:S6819 asks for over `role="button"`.
    const { row } = await renderOneRow();
    expect(row.tagName).toBe("BUTTON");
    expect(row.getAttribute("type")).toBe("button");
  });

  it("does not open a source the row has no chunk for", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse(
        makeResponse([makeRow({ source: { author: "Plato", work: null, section: null } })]),
      ),
    );
    const props = defaultProps();
    const { container } = renderRefs(props);
    await waitFor(() => {
      expect(container.querySelector(".ref-row")).not.toBeNull();
    });
    fireEvent.click(must(container.querySelector(".ref-row")));
    expect(props.onOpenSource).not.toHaveBeenCalled();
  });

  // #720: who decided a row. NULL predates migration 0039 and must read
  // "unrecorded", never "machine".
  it.each([
    ["rejected", "human", "by human"],
    ["rejected", "llm", "by llm"],
    ["rejected", null, "unrecorded"],
    ["manual", null, "unrecorded"],
  ] as const)("a %s row decided by %s shows '%s'", async (status, by, label) => {
    fetchMock.mockResolvedValueOnce(
      okResponse(makeResponse([makeRow({ curator_status: status, curated_by: by })])),
    );
    const { container } = renderRefs(defaultProps());
    await waitFor(() => {
      expect(container.querySelector(".ref-row-curated")?.textContent).toBe(label);
    });
  });

  it("an undecided auto row shows no verdict author", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse(makeResponse([makeRow({ curator_status: "auto", curated_by: null })])),
    );
    const { container } = renderRefs(defaultProps());
    await waitFor(() => expect(container.querySelector(".ref-row")).not.toBeNull());
    expect(container.querySelector(".ref-row-curated")).toBeNull();
  });

  it("an llm-promoted auto row names its verdict author", async () => {
    fetchMock.mockResolvedValueOnce(
      okResponse(makeResponse([makeRow({ curator_status: "auto", curated_by: "llm" })])),
    );
    const { container } = renderRefs(defaultProps());
    await waitFor(() => {
      expect(container.querySelector(".ref-row-curated")?.textContent).toBe("by llm");
    });
  });
});
