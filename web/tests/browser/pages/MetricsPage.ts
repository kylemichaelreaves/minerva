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
    // Fail fast if the route doesn't render at all: this group is
    // unconditional markup, painted before the summary fetch even starts
    // (MetricsPanel.tsx:191), so waiting on it catches a broken route
    // without waiting out the fetch below.
    await this.page.getByRole("group", { name: "Time window", exact: true }).waitFor();
    // Then wait for the summary fetch to actually SETTLE into one of its
    // two terminal states — the table (`rows().length > 0`) or the empty
    // state ("No requests recorded...", MetricsPanel.tsx:332-334) — before
    // returning. This is the difference between `count() === 0` meaning
    // "the server recorded nothing" and meaning "the fetch hasn't
    // resolved yet": `Locator.count()` does not auto-wait, so if `goto()`
    // returned as soon as the (always-present) group appeared,
    // `firstRouteLabel()` below could read a zero-rows table that is
    // simply still loading and throw its "no requests recorded" error
    // against a request that just hasn't finished — a real race, not a
    // hypothetical: `playwright.config.ts` sets `retries: 0`, so it would
    // surface as a hard, unretried CI failure rather than a flake anyone
    // notices as one.
    await this.table.or(this.emptyState).waitFor();
  }

  get table(): Locator {
    return this.page.getByRole("table", { name: "Requests by route", exact: true });
  }

  /** The panel's other terminal state once the summary fetch settles —
   *  the fixture server recorded zero requests in the current window
   *  (MetricsPanel.tsx's `Show ... fallback`). Plain text, not a role:
   *  it's a bare `<div>` with no semantic role to key on, so tiers 1-2 have
   *  nothing to distinguish it by. */
  get emptyState(): Locator {
    return this.page.getByText("No requests recorded in this window.", { exact: true });
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
   *  runs. `metrics.spec.ts` additionally issues its own warm-up
   *  navigation rather than relying on that poll alone — a caveat for
   *  whoever else calls this: that warm-up is a property of that spec
   *  file, not of `goto()` below, so a new caller gets no such guarantee
   *  for free.
   *
   *  Safe to read `count()` synchronously here — not a race — because
   *  `goto()` already waited for `this.table.or(this.emptyState)` to
   *  settle. Without that wait, `count()` (which does not auto-wait,
   *  unlike a Locator action) could read 0 while the summary fetch was
   *  merely still in flight, and this would throw against a request that
   *  simply hadn't finished yet. */
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
