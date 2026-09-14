import { test, expect } from "./fixtures";
import { MetricsPage } from "./pages/MetricsPage";

// DEFAULT_HEIGHT in TimeSeriesChart.tsx:15. Asserting the literal is the
// point: the defect was the height feeding back into the element being
// measured and growing without bound — 164220, then 220348 -> 220828 ->
// 221308 -> 221788, +480px per frame. Any assertion loose enough to accept
// a "reasonable" height would have accepted the first frame of that.
const CHART_HEIGHT = "220";

test.describe("Metrics layout", () => {
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

  test("the route table scrolls internally while the chart stays in view", async ({ page }) => {
    const metrics = new MetricsPage(page);
    await metrics.goto();
    await metrics.selectRoute(await metrics.firstRouteLabel());
    await expect(metrics.chart).toBeInViewport();

    await metrics.table.evaluate((el) => {
      const wrap = el.parentElement;
      if (wrap) wrap.scrollTop = wrap.scrollHeight;
    });

    await expect(metrics.chart).toBeInViewport();
  });
});
