/** The per-request ledger (design variant A).
 *
 *  Filtering is asserted at the REQUEST level, not by counting rendered rows:
 *  `request_spans` is designed to hold years, so narrowing has to happen in
 *  SQL. A test that only checked the rendered output would pass just as
 *  happily against a client-side filter over a full table dump.
 */
import { render, screen, waitFor, fireEvent } from "@solidjs/testing-library";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RequestLedger } from "../src/Metrics/RequestLedger";

const ROW = {
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
const BARE = {
  ...ROW,
  id: "ffffffffffffffff",
  label: "works list",
  method: "GET",
  total_ms: 412,
  accounted_ms: 0,
  unaccounted_ms: 412,
  phases: [],
};

function stub(rows: unknown[]) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: () => Promise.resolve({ window: "24h", since: 0, until: 1, rows, limit: 200 }),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("RequestLedger", () => {
  it("renders one row per request with its unaccounted share", async () => {
    stub([ROW, BARE]);
    render(() => <RequestLedger window="24h" />);
    expect(await screen.findByText("chat")).toBeTruthy();
    expect(screen.getByText("works list")).toBeTruthy();
    // 588 / 5400 = 10.9%; 412 / 412 = 100%
    expect(screen.getByText("100%")).toBeTruthy();
  });

  it("names the phase it carried, and marks the 99.8% that carry none", async () => {
    stub([ROW, BARE]);
    render(() => <RequestLedger window="24h" />);
    expect(await screen.findByText("llm_call")).toBeTruthy();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("asks the SERVER to filter, rather than filtering a full table locally", async () => {
    const f = stub([ROW]);
    render(() => <RequestLedger window="24h" />);
    await screen.findByText("chat");

    fireEvent.click(screen.getByLabelText("Errors only"));
    await waitFor(() => {
      const urls = f.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes("errors=1"))).toBe(true);
    });
  });

  it("passes the has-a-phase filter through as well", async () => {
    const f = stub([ROW]);
    render(() => <RequestLedger window="24h" />);
    await screen.findByText("chat");

    fireEvent.click(screen.getByLabelText("Has a phase"));
    await waitFor(() => {
      const urls = f.mock.calls.map((c) => String(c[0]));
      expect(urls.some((u) => u.includes("phased=1"))).toBe(true);
    });
  });

  it("shows the selected request's breakdown", async () => {
    stub([ROW, BARE]);
    render(() => <RequestLedger window="24h" />);
    fireEvent.click(await screen.findByText("chat"));
    const detail = await screen.findByRole("region", { name: "Request detail" });
    expect(detail.textContent).toContain("a1b2c3d4e5f60718");
    expect(detail.textContent).toContain("llm_call");
  });

  it("explains an empty result rather than showing a bare table", async () => {
    stub([]);
    render(() => <RequestLedger window="24h" />);
    expect(await screen.findByText(/no requests/i)).toBeTruthy();
  });

  it("surfaces a fetch failure instead of rendering an empty table", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));
    render(() => <RequestLedger window="24h" />);
    expect(await screen.findByText(/couldn't load/i)).toBeTruthy();
  });
});
