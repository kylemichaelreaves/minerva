import { test, expect } from "./fixtures";
import { MetricsPage } from "./pages/MetricsPage";

// DEFAULT_HEIGHT in TimeSeriesChart.tsx:15. Asserting the literal is the
// point: the defect was the height feeding back into the element being
// measured and growing without bound — 164220, then 220348 -> 220828 ->
// 221308 -> 221788, +480px per frame. Any assertion loose enough to accept
// a "reasonable" height would have accepted the first frame of that.
const CHART_HEIGHT = "220";

test.describe("Metrics layout", () => {
  test.beforeEach(async ({ page }) => {
    // Explicit warm-up: navigating the landing route first drives at
    // least one recorded request before any test here reads the list.
    // Without this, `firstRouteLabel()` would depend silently on
    // `fixtureServer.ts`'s own startup `/api/health` poll being the thing
    // that seeded the first row (see MetricsPage.firstRouteLabel) — true
    // today, but not this suite's own doing.
    await page.goto("/#/");
  });

  test("the trend chart keeps a fixed height", async ({ page }) => {
    const metrics = new MetricsPage(page);
    await metrics.goto();
    await metrics.selectRoute(await metrics.firstRouteLabel());

    await expect(metrics.chart).toHaveAttribute("height", CHART_HEIGHT);

    // A single reading cannot distinguish "fixed" from "caught on frame one".
    // The runaway loop grew on EVERY frame, so re-read after two of them.
    //
    // Two rAFs, not waitForTimeout: this waits on the same signal the defect
    // rode in on — a ResizeObserver callback scheduled against the frame
    // loop — rather than on wall-clock, which would be a flake waiting to
    // happen on a loaded CI runner.
    await page.evaluate(
      () =>
        new Promise<void>((resolve) => {
          requestAnimationFrame(() =>
            requestAnimationFrame(() => {
              resolve();
            }),
          );
        }),
    );
    await expect(metrics.chart).toHaveAttribute("height", CHART_HEIGHT);
  });

  test("selecting a route shows the chart without scrolling", async ({ page }) => {
    const metrics = new MetricsPage(page);
    await metrics.goto();
    await metrics.selectRoute(await metrics.firstRouteLabel());

    // The chart rendered 780px down — 472px below the fold — so selecting a
    // route updated something the user could not see.
    await expect(metrics.chart).toBeInViewport();
  });

  test("the route list scrolls internally while the chart stays in view", async ({
    page,
    request,
  }) => {
    // Force enough distinct rows that the list cannot show them all at
    // once. `.metrics-routes-scroll` (metrics.css:260-267) is
    // `min-height: 8rem` with `overflow-y: auto`, and each distinct route
    // label the server has recorded becomes its own row
    // (`RouteList.tsx`'s `sorted`). Explicit and deterministic rather
    // than relying on however many labels other tests or hooks happen to
    // have produced by this point in the run: without enough distinct
    // rows, `scrollHeight === clientHeight` and the scroll below is a
    // no-op that would pass identically whether or not the list can
    // actually scroll.
    for (const path of [
      "/api/health",
      "/api/landing/stats",
      "/api/conversations",
      "/api/works",
      "/api/references",
      "/api/references/review_queue",
      "/api/network/summary",
      "/api/terms",
    ]) {
      await request.get(path);
    }

    const metrics = new MetricsPage(page);
    await metrics.goto();
    await metrics.selectRoute(await metrics.firstRouteLabel());
    await expect(metrics.chart).toBeInViewport();

    await metrics.scrollListToBottom();

    // The assertion that makes this test mean something: if the list
    // were NOT internally scrollable (the regression this test guards
    // against — the container growing to fit its content instead of
    // scrolling it), scrollTop would still read 0 here.
    const scrollTop = await metrics.listScrollTop();
    expect(scrollTop).toBeGreaterThan(0);

    await expect(metrics.chart).toBeInViewport();
  });
});
