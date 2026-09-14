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
    // THREE mutually-exclusive terminal states (MetricsPanel.tsx:324-334):
    // the route table (`rows().length > 0`), the empty state ("No
    // requests recorded...", role="status"), or the error alert
    // (`summaryFailed()`, role="alert") — before returning. Waiting on
    // only the first two would hang forever on a genuine fetch failure,
    // since neither ever appears in that case (both live under
    // `<Show when={!summaryFailed()}>`, MetricsPanel.tsx:330).
    //
    // Waiting at all (rather than just the group above) matters because
    // `Locator.count()` does not auto-wait: if `goto()` returned as soon
    // as the (always-present) group appeared, `firstRouteLabel()` below
    // could read a zero-rows table that is simply still loading and
    // throw its "no requests recorded" error against a request that just
    // hasn't finished — a real race, not a hypothetical:
    // `playwright.config.ts` sets `retries: 0`, so it would surface as a
    // hard, unretried CI failure rather than a flake anyone notices as
    // one.
    await this.table.or(this.emptyState).or(this.errorAlert).waitFor();
    // Turn a failed summary fetch into an informative throw here, not a
    // `firstRouteLabel()` guard that never fires and not a timeout
    // anywhere downstream: this is the one place that knows the wait
    // above resolved via the alert rather than real data.
    if ((await this.errorAlert.count()) > 0) {
      const text = (await this.errorAlert.textContent())?.trim() ?? "(no message)";
      throw new Error(`the metrics summary request failed: "${text}"`);
    }
  }

  get table(): Locator {
    return this.page.getByRole("table", { name: "Requests by route", exact: true });
  }

  /** The panel's second terminal state once the summary fetch settles —
   *  the fixture server recorded zero requests in the current window
   *  (MetricsPanel.tsx's `Show ... fallback`). `role="status"`
   *  (MetricsPanel.tsx:334) rather than the earlier version's literal
   *  copy match: an empty state is exactly what `status` is for (it
   *  should be announced to assistive tech), and it happens to make this
   *  locator robust to a copy change instead of dependent on it.
   *
   *  Scoped to `<main>`: the app also renders a global toast container
   *  with `role="status"` (`components/primitives/Toasts.tsx`) as a
   *  sibling of `<main>`, not inside it (`App.tsx:212-229`) — an
   *  unscoped `getByRole("status")` matches both and Playwright's
   *  strict mode refuses to wait on an ambiguous match. */
  get emptyState(): Locator {
    return this.page.getByRole("main").getByRole("status");
  }

  /** The panel's third terminal state — the summary fetch itself failed
   *  (`summaryFailed()`, MetricsPanel.tsx:324-328). Scoped to `<main>`
   *  for the same reason as `emptyState` above, and additionally: only
   *  one alert can be showing there at `goto()` time anyway, since the
   *  OTHER two `role="alert"` elements this component renders (the
   *  detail/series errors, MetricsPanel.tsx:237,259) live under
   *  `<Show when={selectedLabel()}>` and can't appear before a route is
   *  selected. */
  get errorAlert(): Locator {
    return this.page.getByRole("main").getByRole("alert");
  }

  /** The chart's own name, from TimeSeriesChart.tsx:148-149. */
  get chart(): Locator {
    return this.page.getByRole("img", { name: /Latency over time/ });
  }

  /** Scrolls the table's scroll container (`.metrics-table-wrap`,
   *  metrics.css:166-174) to its bottom. Mechanism lives here, not in the
   *  spec: `<table>` itself doesn't scroll, its parent wrapper does. */
  async scrollTableToBottom(): Promise<void> {
    await this.table.evaluate((el) => {
      const wrap = el.parentElement;
      if (wrap) wrap.scrollTop = wrap.scrollHeight;
    });
  }

  /** The table's scroll container's current `scrollTop`, or 0 if for some
   *  reason the table has no parent. */
  async tableScrollTop(): Promise<number> {
    return this.table.evaluate((el) => el.parentElement?.scrollTop ?? 0);
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
   *  `goto()` already waited for the summary fetch to settle into one of
   *  its three terminal states, and already threw its own error if that
   *  state was the failure alert (so getting here means it was the table
   *  or the empty state). Without that wait, `count()` (which does not
   *  auto-wait, unlike a Locator action) could read 0 while the summary
   *  fetch was merely still in flight, and this would throw against a
   *  request that simply hadn't finished yet. */
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
