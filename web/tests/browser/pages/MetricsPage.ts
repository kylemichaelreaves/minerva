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
    // unconditional markup inside the panel header, painted before the
    // summary fetch even starts (MetricsPanel.tsx's `metrics-windows`),
    // so waiting on it catches a broken route without waiting out the
    // fetch below.
    await this.page.getByRole("group", { name: "Time window", exact: true }).waitFor();
    // Then wait for the summary fetch to actually SETTLE into one of its
    // THREE mutually-exclusive terminal states — all three now live in
    // `RouteList.tsx` rather than `MetricsPanel.tsx`, since #600 split
    // the list out: the route list (`entries.length > 0`), the empty
    // state ("No requests recorded...", role="status"), or the error
    // alert (`errorText`, role="alert") — before returning. Waiting on
    // only the first two would hang forever on a genuine fetch failure,
    // since neither ever appears in that case (both live under
    // `<Show when={props.errorText === undefined}>`).
    //
    // Waiting at all (rather than just the group above) matters because
    // `Locator.count()` does not auto-wait: if `goto()` returned as soon
    // as the (always-present) group appeared, `firstRouteLabel()` below
    // could read a zero-row list that is simply still loading and
    // throw its "no requests recorded" error against a request that just
    // hasn't finished — a real race, not a hypothetical:
    // `playwright.config.ts` sets `retries: 0`, so it would surface as a
    // hard, unretried CI failure rather than a flake anyone notices as
    // one.
    await this.routeList.or(this.emptyState).or(this.errorAlert).waitFor();
    // Turn a failed summary fetch into an informative throw here, not a
    // `firstRouteLabel()` guard that never fires and not a timeout
    // anywhere downstream: this is the one place that knows the wait
    // above resolved via the alert rather than real data.
    if ((await this.errorAlert.count()) > 0) {
      const text = (await this.errorAlert.textContent())?.trim() ?? "(no message)";
      throw new Error(`the metrics summary request failed: "${text}"`);
    }
  }

  /** The route list. #600 rebuilt this surface around triage: the route
   *  TABLE is now a list of toggle buttons grouped by severity
   *  (`RouteList.tsx`), so `getByRole("table", { name: "Requests by
   *  route" })` no longer resolves. Same tier-1 locator, new role —
   *  `role="group"` with the name the list now carries. */
  get routeList(): Locator {
    return this.page.getByRole("group", { name: "Routes", exact: true });
  }

  /** The panel's second terminal state once the summary fetch settles —
   *  the fixture server recorded zero requests in the current window
   *  (`RouteList.tsx`'s `Show ... fallback`). `role="status"`
   *  rather than the earlier version's literal
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
   *  (`RouteList.tsx`'s `errorText`). Scoped to `<main>` for the same
   *  reason as `emptyState` above, and additionally: only one alert can
   *  be showing there at `goto()` time anyway, since the OTHER two
   *  `role="alert"` elements this surface renders (the series and
   *  breakdown errors, `RouteDetail.tsx`) live under MetricsPanel's
   *  `<Show when={selectedEntry()}>` and can't appear before a route is
   *  selected. */
  get errorAlert(): Locator {
    return this.page.getByRole("main").getByRole("alert");
  }

  /** The chart's own name, from `TimeSeriesChart.tsx`'s `aria-label`. */
  get chart(): Locator {
    return this.page.getByRole("img", { name: /Latency over time/ });
  }

  /** Scrolls the route list to its bottom. Mechanism lives here, not in
   *  the spec. Note the element scrolled is the group ITSELF, not its
   *  parent: `.metrics-routes-scroll` (metrics.css:260-267) is both the
   *  `overflow-y: auto` container and the thing carrying `role="group"`.
   *  The old table needed `parentElement` because a `<table>` does not
   *  scroll and its `.metrics-table-wrap` did. */
  async scrollListToBottom(): Promise<void> {
    await this.routeList.evaluate((el) => {
      el.scrollTop = el.scrollHeight;
    });
  }

  /** The route list's current `scrollTop`. */
  async listScrollTop(): Promise<number> {
    return this.routeList.evaluate((el) => el.scrollTop);
  }

  /** A row identified by the route it reports, via the data-testid the
   *  rebuild kept (`RouteList.tsx`'s `Row`). Tier 1 still cannot
   *  distinguish rows: a row's accessible name concatenates its every
   *  span — label, method, error rate, count, p95 — and the last three
   *  change between runs.
   *
   *  `button`, not `row`: #600's rows are `<button aria-pressed>`, which
   *  is what makes them announce their selected state at all. */
  routeRow(label: string): Locator {
    return this.routeList.getByRole("button").filter({
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
   *  route before any spec
   *  runs. `metrics.spec.ts` additionally issues its own warm-up
   *  navigation rather than relying on that poll alone — a caveat for
   *  whoever else calls this: that warm-up is a property of that spec
   *  file, not of `goto()` below, so a new caller gets no such guarantee
   *  for free.
   *
   *  Safe to read `count()` synchronously here — not a race — because
   *  `goto()` already waited for the summary fetch to settle into one of
   *  its three terminal states, and already threw its own error if that
   *  state was the failure alert (so getting here means it was the list
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
