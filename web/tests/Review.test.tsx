import { describe, it, expect, beforeEach, afterEach, vi, type MockedFunction } from "vitest";
import { render, waitFor } from "@solidjs/testing-library";
import { fireEvent } from "./helpers/settledFireEvent";
import Review, { type ReviewProps } from "~/features/Refs/components/Review";
import { MobileShellProvider } from "~/components/shell/MobileShellContext";
import type { ReviewQueueResponse, ReviewQueueRow } from "~/api/refsApi";
import { okResponse } from "./helpers/testRouting";
import { must } from "./helpers/must";

let fetchMock: MockedFunction<typeof fetch>;

function makeRow(overrides: Partial<ReviewQueueRow> = {}): ReviewQueueRow {
  return {
    id: 10,
    source_chunk_id: "rep-509d",
    source_span_start: null,
    source_span_end: null,
    source_form: null,
    quoted_phrase: null,
    target: {
      author: "Aristotle",
      work: "Ethics",
      in_corpus_work_id: 2,
      chunk_id: "ne-1",
      locator: "1097b",
      locator_payload: null,
      sort_key: null,
    },
    reference_type: "cites",
    confidence: 0.4,
    source_method: "rule+embed",
    curator_status: "auto",
    curated_by: null,
    curated_at: null,
    note: null,
    source: {
      author: "Plato",
      work: "Republic",
      section: "509d",
      text: "Source passage text.",
    },
    ...overrides,
  };
}

function makeQueue(rows: ReviewQueueRow[]): ReviewQueueResponse {
  return {
    limit: 50,
    offset: 0,
    total_pending: rows.length,
    references: rows,
  };
}

function renderReview(props: ReviewProps) {
  return render(() => (
    <MobileShellProvider>
      <Review {...props} />
    </MobileShellProvider>
  ));
}

function defaultProps(overrides: Partial<ReviewProps> = {}): ReviewProps {
  return {
    onNavigate: vi.fn(),
    onNavigateToReference: vi.fn(),
    onOpenSource: vi.fn(),
    ...overrides,
  };
}

describe("<Review />", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads the queue and renders the current row", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/references/review_queue")) {
        return Promise.resolve(okResponse(makeQueue([makeRow(), makeRow({ id: 11 })])));
      }
      if (url.includes("/api/references/sources")) {
        return Promise.resolve(okResponse({ sources: ["Plato"], targets: ["Aristotle"] }));
      }
      return Promise.resolve(okResponse({}));
    });

    const { container } = renderReview(defaultProps());
    await waitFor(() => {
      expect(container.querySelector(".review-card")).not.toBeNull();
    });
    expect(container.textContent).toContain("2 pending");
    expect(container.textContent).toContain("Republic");
  });

  it("approve patches curation and advances the cursor", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/references/review_queue")) {
        return Promise.resolve(okResponse(makeQueue([makeRow(), makeRow({ id: 11 })])));
      }
      if (url.includes("/api/references/sources")) {
        return Promise.resolve(okResponse({ sources: ["Plato"], targets: ["Aristotle"] }));
      }
      if (init?.method === "PATCH") {
        return Promise.resolve(okResponse(makeRow({ id: 10, curator_status: "approved" })));
      }
      return Promise.resolve(okResponse({}));
    });

    const props = defaultProps();
    const { container } = renderReview(props);
    await waitFor(() => {
      expect(container.querySelector(".review-btn-approve")).not.toBeNull();
    });
    fireEvent.click(must(container.querySelector(".review-btn-approve")));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true);
    });
    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(patchCall?.[1]?.body as string)).toMatchObject({
      curator_status: "approved",
    });
    await waitFor(() => {
      expect(props.onNavigateToReference).toHaveBeenLastCalledWith(11);
    });
  });

  it("reject patches with rejected status", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/references/review_queue")) {
        return Promise.resolve(okResponse(makeQueue([makeRow()])));
      }
      if (url.includes("/api/references/sources")) {
        return Promise.resolve(okResponse({ sources: ["Plato"], targets: ["Aristotle"] }));
      }
      if (init?.method === "PATCH") {
        return Promise.resolve(okResponse(makeRow({ curator_status: "rejected" })));
      }
      return Promise.resolve(okResponse({}));
    });

    const { container } = renderReview(defaultProps());
    await waitFor(() => {
      expect(container.querySelector(".review-btn-reject")).not.toBeNull();
    });
    fireEvent.click(must(container.querySelector(".review-btn-reject")));
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true);
    });
    const patchCall = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
    expect(JSON.parse(patchCall?.[1]?.body as string)).toMatchObject({
      curator_status: "rejected",
    });
  });

  it("skip advances without PATCH", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/references/review_queue")) {
        return Promise.resolve(okResponse(makeQueue([makeRow(), makeRow({ id: 11 })])));
      }
      if (url.includes("/api/references/sources")) {
        return Promise.resolve(okResponse({ sources: ["Plato"], targets: ["Aristotle"] }));
      }
      return Promise.resolve(okResponse({}));
    });

    const props = defaultProps();
    const { container } = renderReview(props);
    await waitFor(() => {
      expect(container.querySelector(".review-btn-skip")).not.toBeNull();
    });
    fireEvent.click(must(container.querySelector(".review-btn-skip")));
    await waitFor(() => {
      expect(props.onNavigateToReference).toHaveBeenLastCalledWith(11);
    });
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });

  it("syncs a stale referenceId to the landed row on load", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/references/review_queue")) {
        return Promise.resolve(okResponse(makeQueue([makeRow({ id: 10 }), makeRow({ id: 11 })])));
      }
      if (url.includes("/api/references/sources")) {
        return Promise.resolve(okResponse({ sources: ["Plato"], targets: ["Aristotle"] }));
      }
      return Promise.resolve(okResponse({}));
    });

    const props = defaultProps({ referenceId: 999 });
    renderReview(props);
    await waitFor(() => {
      expect(props.onNavigateToReference).toHaveBeenCalledWith(10);
    });
  });

  it("shows empty state when the queue has no rows", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/references/review_queue")) {
        return Promise.resolve(okResponse(makeQueue([])));
      }
      if (url.includes("/api/references/sources")) {
        return Promise.resolve(okResponse({ sources: [], targets: [] }));
      }
      return Promise.resolve(okResponse({}));
    });

    const { container } = renderReview(defaultProps());
    await waitFor(() => {
      expect(container.textContent).toContain("No more rows pending");
    });
  });

  it("fetches the next page at an offset shifted by decided rows", async () => {
    // Regression: approve/reject decisions remove rows from the
    // server-side pending queue, so after deciding all N locally
    // loaded rows the next unseen row sits at server offset 0 — not
    // offset N. The old code fetched at the local row count and
    // skipped that many still-pending rows.
    const queueCalls: string[] = [];
    fetchMock.mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/references/review_queue")) {
        queueCalls.push(url);
        if (queueCalls.length === 1) {
          return Promise.resolve(
            okResponse({
              limit: 50,
              offset: 0,
              total_pending: 3,
              references: [makeRow({ id: 10 }), makeRow({ id: 11 })],
            }),
          );
        }
        // After two approvals the server queue holds one row.
        return Promise.resolve(
          okResponse({
            limit: 50,
            offset: 0,
            total_pending: 1,
            references: [makeRow({ id: 12 })],
          }),
        );
      }
      if (url.includes("/api/references/sources")) {
        return Promise.resolve(okResponse({ sources: ["Plato"], targets: ["Aristotle"] }));
      }
      if (init?.method === "PATCH") {
        return Promise.resolve(okResponse(makeRow({ curator_status: "approved" })));
      }
      return Promise.resolve(okResponse({}));
    });

    const props = defaultProps();
    const { container } = renderReview(props);
    await waitFor(() => {
      expect(container.querySelector(".review-btn-approve")).not.toBeNull();
    });

    // Approve row 10 → advance to row 11 (still local, no refetch).
    fireEvent.click(must(container.querySelector(".review-btn-approve")));
    await waitFor(() => {
      expect(props.onNavigateToReference).toHaveBeenLastCalledWith(11);
    });
    expect(queueCalls.length).toBe(1);
    // The approve button is disabled while the first decision is in flight,
    // and comes back a flush after the advance (Solid 2 commits the
    // `acting` reset at the next microtask) — a click before then is a
    // click on a disabled button.
    await waitFor(() => {
      expect(container.querySelector(".review-btn-approve")).not.toBeDisabled();
    });

    // Approve row 11 → local rows exhausted → next page fetched. Both
    // loaded rows were decided, so the fetch must ask for offset 0.
    fireEvent.click(must(container.querySelector(".review-btn-approve")));
    await waitFor(() => {
      expect(props.onNavigateToReference).toHaveBeenLastCalledWith(12);
    });
    expect(queueCalls.length).toBe(2);
    expect(queueCalls[1]).toContain("offset=0");
    expect(container.textContent).toContain("1 pending");
  });

  it("keyboard j navigates forward without PATCH", async () => {
    fetchMock.mockImplementation((input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/references/review_queue")) {
        return Promise.resolve(okResponse(makeQueue([makeRow(), makeRow({ id: 11 })])));
      }
      if (url.includes("/api/references/sources")) {
        return Promise.resolve(okResponse({ sources: ["Plato"], targets: ["Aristotle"] }));
      }
      return Promise.resolve(okResponse({}));
    });

    const props = defaultProps();
    renderReview(props);
    await waitFor(() => {
      expect(props.onNavigateToReference).toHaveBeenCalledWith(10);
    });
    fireEvent.keyDown(document.body, { key: "j" });
    await waitFor(() => {
      expect(props.onNavigateToReference).toHaveBeenLastCalledWith(11);
    });
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(false);
  });
});
