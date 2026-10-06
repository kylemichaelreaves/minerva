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
      "/api/references/sources",
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

// The route-name column, measured rather than eyeballed. The reported
// defect: at a 1280px panel the list was capped at 420px, and once the
// severity dot and method badge had taken their share the name column came
// to ~84px — `conversation delete` wanted 136px and got 62.
//
// Measured on `.metrics-row-name`, the flex CONTAINER, not on
// `.metrics-row-text`: the text node is a flex item, so its clientWidth
// collapses to its own content when the label is short. Measuring it would
// report the label's width rather than the space available, and pass or
// fail on whichever route the fixture happened to record first.
//
// 210px is derived, not chosen: the longest real label renders at 136px,
// plus a DELETE badge (~55), the severity dot (7) and two gaps (16).
const LONGEST_REAL_ROW_PX = 210;

test("a route name has room for the longest real label", async ({ page }) => {
  const metrics = new MetricsPage(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await metrics.goto();
  await metrics.selectRoute(await metrics.firstRouteLabel());

  const width = await page
    .locator(".metrics-row-name")
    .first()
    .evaluate((el) => el.getBoundingClientRect().width);
  expect(width).toBeGreaterThan(LONGEST_REAL_ROW_PX);
});

test("no route name in the list is truncated", async ({ page }) => {
  // Complements the width floor above: that one encodes the requirement,
  // this one catches a regression against whatever labels are actually
  // present, including any the fixture gains later.
  const metrics = new MetricsPage(page);
  await page.setViewportSize({ width: 1280, height: 900 });
  await metrics.goto();
  await metrics.selectRoute(await metrics.firstRouteLabel());

  const clipped = await page
    .locator(".metrics-row-text")
    .evaluateAll((els) =>
      els.filter((el) => el.scrollWidth > el.clientWidth + 1).map((el) => el.textContent),
    );
  expect(clipped).toEqual([]);
});

test("the two-pane split collapses when the PANEL is too narrow", async ({ page }) => {
  // Not when the viewport is. The panel sits inside app chrome, so at a
  // 900px viewport it is only ~609px wide — two columns had already
  // stopped fitting while the 768px viewport breakpoint had not fired,
  // leaving the detail pane a few dozen pixels.
  const metrics = new MetricsPage(page);
  await page.setViewportSize({ width: 900, height: 900 });
  await metrics.goto();
  await metrics.selectRoute(await metrics.firstRouteLabel());

  const columns = await page
    .locator(".metrics-split")
    .evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(" ").length);
  expect(columns).toBe(1);
});
