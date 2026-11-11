/** "Load older" over a keyset cursor.
 *
 *  Offset paging would drift — `request_spans` is append-only and sorted
 *  newest-first, so a row arriving between two fetches pushes the window down
 *  and the reader sees the same request twice. The cursor names a position in
 *  the ordering instead, and the server hands it back rather than making the
 *  client rebuild it from the last row.
 */
import { render, screen, fireEvent, waitFor } from "@solidjs/testing-library";
import { createSignal } from "solid-js";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MetricWindow } from "../src/api/metricsApi";
import { RequestLedger } from "../src/Metrics/RequestLedger";

const T0 = 1_700_000_000;

function row(n: number) {
  return {
    id: `id${String(n).padStart(4, "0")}`,
    at: T0 + n,
    label: `route-${n}`,
    method: "GET",
    status: 200,
    total_ms: 10,
    accounted_ms: 0,
    unaccounted_ms: 10,
    phases: [],
    cpu_ms: null,
    sqlite_ms: null,
    sqlite_queries: null,
  };
}

function page(rows: unknown[], hasMore: boolean, last?: { at: number; id: string }) {
  return {
    window: "all",
    since: 0,
    until: 1,
    rows,
    limit: 2,
    has_more: hasMore,
    next_before: hasMore && last ? last : null,
  };
}

function stubPages(...pages: unknown[]) {
  const fetchMock = vi.fn();
  for (const p of pages) {
    fetchMock.mockResolvedValueOnce({ ok: true, status: 200, json: () => Promise.resolve(p) });
  }
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("RequestLedger paging", () => {
  it("offers to load older only when there is more", async () => {
    stubPages(page([row(9), row(8)], true, { at: T0 + 8, id: "id0008" }));
    render(() => <RequestLedger window="all" />);
    expect(await screen.findByRole("button", { name: /older/i })).toBeTruthy();
  });

  it("hides the control on the last page", async () => {
    stubPages(page([row(9)], false));
    render(() => <RequestLedger window="all" />);
    await screen.findByText("route-9");
    expect(screen.queryByRole("button", { name: /older/i })).toBeNull();
  });

  it("sends the cursor the server handed back", async () => {
    const f = stubPages(
      page([row(9), row(8)], true, { at: T0 + 8, id: "id0008" }),
      page([row(7)], false),
    );
    render(() => <RequestLedger window="all" />);
    fireEvent.click(await screen.findByRole("button", { name: /older/i }));

    await waitFor(() => {
      const urls = f.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes("before_id=id0008"))).toBe(true);
      expect(urls.some((u) => u.includes(`before_at=${T0 + 8}`))).toBe(true);
    });
  });

  it("appends the older page rather than replacing it", async () => {
    stubPages(page([row(9), row(8)], true, { at: T0 + 8, id: "id0008" }), page([row(7)], false));
    render(() => <RequestLedger window="all" />);
    fireEvent.click(await screen.findByRole("button", { name: /older/i }));

    expect(await screen.findByText("route-7")).toBeTruthy();
    expect(screen.getByText("route-9")).toBeTruthy();
  });

  it("starts over when a filter changes", async () => {
    // Otherwise the appended pages describe the PREVIOUS filter and the two
    // sets are silently interleaved.
    stubPages(
      page([row(9), row(8)], true, { at: T0 + 8, id: "id0008" }),
      page([row(7)], false),
      page([row(5)], false),
    );
    render(() => <RequestLedger window="all" />);
    fireEvent.click(await screen.findByRole("button", { name: /older/i }));
    await screen.findByText("route-7");

    fireEvent.click(screen.getByLabelText("Errors only"));

    await waitFor(() => expect(screen.queryByText("route-9")).toBeNull());
    expect(await screen.findByText("route-5")).toBeTruthy();
  });

  it("starts over when the window changes (#881)", async () => {
    // The window arrives as a prop and the ledger is not remounted on a
    // switch, so nothing used to drop the appended pages: switching after
    // "Load older" fetched NEW-window rows older than the OLD window's cursor
    // and appended them below the old window's page.
    const f = vi.fn((url: string) => {
      const u = new URL(url, "http://x");
      let body: unknown;
      if (u.searchParams.get("window") === "all") {
        body = u.searchParams.has("before_id")
          ? page([row(7)], false)
          : page([row(9), row(8)], true, { at: T0 + 8, id: "id0008" });
      } else {
        body = page([row(3)], false);
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    });
    vi.stubGlobal("fetch", f);

    const [win, setWin] = createSignal<MetricWindow>("all");
    render(() => <RequestLedger window={win()} />);
    fireEvent.click(await screen.findByRole("button", { name: /older/i }));
    await screen.findByText("route-7");

    setWin("7d");

    expect(await screen.findByText("route-3")).toBeTruthy();
    // Every row on screen belongs to the new window…
    expect(screen.queryByText("route-9")).toBeNull();
    expect(screen.queryByText("route-7")).toBeNull();
    // …and the new window was never asked for rows older than the old cursor.
    const newWindowUrls = f.mock.calls.map((c) => c[0]).filter((u) => u.includes("window=7d"));
    expect(newWindowUrls.length).toBeGreaterThan(0);
    expect(newWindowUrls.some((u) => u.includes("before_"))).toBe(false);
  });
});
