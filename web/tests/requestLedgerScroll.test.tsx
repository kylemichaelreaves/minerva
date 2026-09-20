/** "Load older" has to be reachable, not merely rendered.
 *
 *  It was placed after the table, and the table had no bounded height — so
 *  with a 200-row page it sat roughly 6,600px below the fold. A browser check
 *  using Playwright's `isVisible()` passed anyway: that means "has a
 *  non-empty bounding box", not "the user can see it".
 *
 *  jsdom does no layout, so this asserts the STRUCTURE that bounds the table.
 *  It cannot prove the button is on screen; it does catch the wrapper being
 *  removed again, which is the specific regression.
 */
import { render, screen, waitFor } from "@solidjs/testing-library";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RequestLedger } from "../src/Metrics/RequestLedger";

function rows(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    id: `id${i}`,
    at: 1_700_000_000 + i,
    label: `route-${i}`,
    method: "GET",
    status: 200,
    total_ms: 10,
    accounted_ms: 0,
    unaccounted_ms: 10,
    phases: [],
    cpu_ms: null,
    sqlite_ms: null,
    sqlite_queries: null,
  }));
}

function stub(n: number, hasMore: boolean) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({
          window: "all",
          since: 0,
          until: 1,
          rows: rows(n),
          limit: 200,
          has_more: hasMore,
          next_before: hasMore ? { at: 1_700_000_000, id: "id0" } : null,
        }),
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("RequestLedger reachability", () => {
  it("puts the table inside a bounded scroll container", async () => {
    stub(50, true);
    const { container } = render(() => <RequestLedger window="all" />);
    await screen.findByText("route-0");
    const wrap = container.querySelector(".mledger-tblwrap");
    expect(wrap).not.toBeNull();
    expect(wrap?.querySelector("table.mledger-table")).not.toBeNull();
  });

  it("keeps the control outside that container, not scrolled away with the rows", async () => {
    stub(50, true);
    const { container } = render(() => <RequestLedger window="all" />);
    const button = await screen.findByRole("button", { name: /load older/i });
    expect(container.querySelector(".mledger-tblwrap")?.contains(button)).toBe(false);
  });

  it("still shows the control with a full page of rows", async () => {
    stub(200, true);
    render(() => <RequestLedger window="all" />);
    await waitFor(async () =>
      expect(await screen.findByRole("button", { name: /load older/i })).toBeTruthy(),
    );
  });
});
