// Tests for `<Refs>` — the corpus-wide cross-references browser.
// Covers the filter-fetch-render cycle that the maintainability audit
// flagged as having no test coverage.

import {
  describe,
  it,
  expect,
  beforeEach,
  afterEach,
  vi,
  type MockedFunction,
} from "vitest";
import { render, fireEvent, waitFor } from "@solidjs/testing-library";
import Refs, { type RefsProps } from "~/Refs";
import { MobileShellProvider } from "~/components/MobileShellContext";
import type {
  ReferencesListResponse,
  ReferencesListRow,
} from "~/api/refsApi";

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
    expect(container.querySelector(".refs-meta")?.textContent).toContain(
      "2 references",
    );
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
    const url = fetchMock.mock.calls[0][0] as string;
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
    const checkbox = container.querySelector(
      ".refs-filter-check input[type=checkbox]",
    )!;
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
    fireEvent.click(container.querySelector(".ref-row")!);
    expect(props.onOpenSource).toHaveBeenCalledWith("Republic", "rep-509d");
  });

  it("empty result with active filters shows EmptyState + 'Clear filters'", async () => {
    fetchMock.mockResolvedValueOnce(okResponse(makeResponse([])));
    const props = defaultProps({ sourceAuthor: "Aquinas" });
    const { container } = renderRefs(props);
    await waitFor(() => {
      expect(container.querySelector(".refs-empty")).not.toBeNull();
    });
    const clearBtn = container.querySelector(
      ".refs-clear",
    )!;
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
    fireEvent.click(container.querySelector(".refs-review-link")!);
    expect(onOpenReview).toHaveBeenCalled();
  });
});
