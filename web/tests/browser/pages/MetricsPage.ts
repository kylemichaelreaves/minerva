import type { Locator, Page } from "@playwright/test";

/** Intent-level API for the Metrics route.
 *
 *  Every accessor returns a Locator, never an ElementHandle: a Locator
 *  re-resolves on each use and carries Playwright's auto-waiting, while a
 *  handle is a snapshot that goes stale and then gets "fixed" with a sleep.
 *  Nothing here asserts — assertions belong in specs, so a failure names the
 *  behaviour that broke rather than a helper. Same discipline as
 *  `ReaderPage`. */
export class MetricsPage {
  constructor(private readonly page: Page) {}

  async goto(): Promise<void> {
    await this.page.goto("/#/metrics");
    // Wait on the window-selector, not the table: the table only mounts
    // once at least one route has been recorded (`rows().length > 0`,
    // MetricsPanel.tsx:332) — a cold server with zero recorded requests
    // renders "No requests recorded in this window." instead, and the
    // table would never appear at all. Waiting on the group (present in
    // both cases) keeps `goto()` itself agnostic to that, so a genuine
    // zero-rows server is reported by `firstRouteLabel()`'s own check
    // below instead of an opaque `waitFor` timeout here.
    await this.page.getByRole("group", { name: "Time window", exact: true }).waitFor();
  }

  get table(): Locator {
    return this.page.getByRole("table", { name: "Requests by route", exact: true });
  }

  /** The chart's own name, from TimeSeriesChart.tsx:148-149. */
  get chart(): Locator {
    return this.page.getByRole("img", { name: /Latency over time/ });
  }

  /** A row identified by the route it reports, via the one pre-existing
   *  data-testid in the codebase (MetricsPanel.tsx:357). Tier 1 cannot
   *  distinguish rows: a row's accessible name concatenates every cell,
   *  including counts that change between runs. */
  routeRow(label: string): Locator {
    return this.table.getByRole("row").filter({
      has: this.page
        .getByTestId("metrics-route-label")
        .and(this.page.getByText(label, { exact: true })),
    });
  }

  async selectRoute(label: string): Promise<void> {
    await this.routeRow(label).click();
  }

  /** The first route label the server actually reported. Derived, because
   *  which routes appear depends on what the suite happened to request —
   *  and, today, also on `fixtureServer.ts`'s own startup `/api/health`
   *  poll (`waitForHealth`), which is itself recorded as the `health`
   *  route (`router.py:99`, timed at `serve.py:391`) before any spec
   *  runs. Each spec that calls this also issues its own warm-up
   *  navigation rather than relying on that poll alone.
   *
   *  `count()` first, not a bare `.textContent()`: a Locator action
   *  auto-waits for its element to appear, so checking emptiness only
   *  after `.textContent()` would hang until the test timeout on a
   *  genuine zero-rows server instead of ever reaching this check. */
  async firstRouteLabel(): Promise<string> {
    const cells = this.page.getByTestId("metrics-route-label");
    if ((await cells.count()) === 0) {
      throw new Error(
        "no route rows rendered — the server recorded no requests. Not " +
          "skipping (#133): the suite has already driven the API by this point.",
      );
    }
    const text = (await cells.first().textContent())?.trim();
    if (!text) {
      throw new Error(
        "a route-label cell rendered with no text — the row exists but its " +
          "label is empty. Not skipping (#133).",
      );
    }
    return text;
  }
}
