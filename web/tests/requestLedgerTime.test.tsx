/** The Requests table's time column carries a date.
 *
 *  It rendered `HH:MM:SS` only. The window selector goes to `7d`, `30d` and
 *  `all`, so two rows from different days were indistinguishable — and the
 *  table is sorted newest-first, which makes the repetition look like a
 *  cluster of requests one second apart rather than a week apart.
 *
 *  UTC throughout, matching the rest of the surface: mixing a local date with
 *  a UTC clock would be worse than either.
 */
import { render, screen, fireEvent } from "@solidjs/testing-library";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RequestLedger } from "../src/Metrics/RequestLedger";

// 2026-09-19T14:23:01Z and 2026-09-12T14:23:01Z — same clock, seven days apart.
const LATER = Date.UTC(2026, 8, 19, 14, 23, 1) / 1000;
const EARLIER = Date.UTC(2026, 8, 12, 14, 23, 1) / 1000;

function row(at: number, id: string) {
  return {
    id,
    at,
    label: "works list",
    method: "GET",
    status: 200,
    total_ms: 12,
    accounted_ms: 0,
    unaccounted_ms: 12,
    phases: [],
    cpu_ms: null,
    sqlite_ms: null,
    sqlite_queries: null,
  };
}

function stub(rows: unknown[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ window: "7d", since: 0, until: 1, rows, limit: 200 }),
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("RequestLedger time column", () => {
  it("distinguishes two requests a week apart at the same clock time", async () => {
    stub([row(LATER, "a"), row(EARLIER, "b")]);
    render(() => <RequestLedger window="7d" />);
    await screen.findAllByText("works list");

    const cells = screen.getAllByText(/14:23:01/);
    expect(cells).toHaveLength(2);
    const [first, second] = cells;
    expect(first?.textContent).not.toBe(second?.textContent);
    expect(first?.textContent).toBeTruthy();
  });

  it("shows the date as well as the clock", async () => {
    stub([row(LATER, "a")]);
    render(() => <RequestLedger window="7d" />);
    const cell = await screen.findByText(/14:23:01/);
    expect(cell.textContent).toMatch(/09-19/);
  });

  it("stays in UTC, matching the rest of the surface", async () => {
    // Chosen at a UTC instant that falls on the PREVIOUS day in negative
    // offsets and the NEXT day in positive ones, so a local-time slip shows.
    const edge = Date.UTC(2026, 8, 19, 23, 30, 0) / 1000;
    stub([row(edge, "a")]);
    render(() => <RequestLedger window="7d" />);
    const cell = await screen.findByText(/23:30:00/);
    expect(cell.textContent).toMatch(/09-19/);
  });

  it("keeps the detail panel's timestamp labelled UTC", async () => {
    stub([row(LATER, "a")]);
    render(() => <RequestLedger window="7d" />);
    fireEvent.click(await screen.findByText("works list"));
    const detail = await screen.findByRole("region", { name: "Request detail" });
    expect(detail.textContent).toMatch(/UTC/);
  });
});
