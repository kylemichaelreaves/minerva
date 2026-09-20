import type { Page } from "@playwright/test";

import { test, expect } from "./fixtures";
import { MetricsPage } from "./pages/MetricsPage";

// Switching the time window refetches every resource on the surface. The
// defect: all of them were gated on `resource.loading`, which is true during
// a REFRESH as well as a first load, so the previous window's data — still
// held in the resource, because Solid's `load()` never clears `value` — was
// unmounted rather than shown. Measured against the real server, everything
// below the header jumped 94px up and back inside one ~39ms frame, and the
// Requests tab's count caption blinked out for 251ms.
//
// Both tests below hold the refetch open rather than racing it. No
// `waitForTimeout`: a transient state asserted against wall-clock is the
// flaky test this suite refuses to have. The request is held until the
// assertions are done, so the window under test is unbounded.

interface Deferred {
  promise: Promise<void>;
  resolve: () => void;
}

/** A promise with its resolver exposed. Written out rather than inlined as
 *  `new Promise((r) => (resolve = r))` so nothing needs a definite-assignment
 *  assertion or an assignment buried in an expression. */
function deferred(): Deferred {
  let settle: () => void = () => undefined;
  const promise = new Promise<void>((resolve) => {
    settle = resolve;
  });
  return { promise, resolve: () => settle() };
}

interface HeldRequests {
  /** Resolves once the first metrics request has arrived — the
   *  deterministic signal that the refresh has actually started. */
  started: Promise<void>;
  /** Lets the parked requests through.
   *
   *  Deliberately not `page.unroute`: tearing the handler down while a
   *  request is still parked inside it fails with "Route is already
   *  handled!". Released handlers continue normally, and the next
   *  navigation drops them. */
  release: () => void;
}

/** Holds every metrics request until `release()` is called, so a transient
 *  state can be asserted without racing it. */
async function holdMetricsRequests(page: Page): Promise<HeldRequests> {
  const arrival = deferred();
  const held = deferred();

  await page.route("**/api/metrics/**", async (route) => {
    arrival.resolve();
    await held.promise;
    await route.continue();
  });

  return { started: arrival.promise, release: held.resolve };
}

/** Waits two animation frames, so Solid's render of the refreshing state has
 *  certainly landed. Same mechanism the trend-chart test uses, and the same
 *  reason: this waits on the frame loop the render rides in on rather than
 *  on a clock. */
async function settleFrames(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
}

/** Named once so neither the in-page reads nor the opacity checks repeat a
 *  literal. Passed INTO `page.evaluate`, since that callback runs in the
 *  browser and cannot close over anything from this scope. */
const SEL = {
  verdict: ".metrics-verdict",
  views: ".metrics-views",
  row: ".metrics-row",
  ledgerCount: ".mledger-count",
} as const;

interface Shot {
  verdict: number;
  verdictHeight: number;
  viewsTop: number;
  rows: number;
}

/** One synchronous read of the DOM. Everything here is a plain value rather
 *  than a Playwright matcher on purpose — see the note on retrying matchers
 *  in the second test. */
function shoot(page: Page): Promise<Shot> {
  return page.evaluate((sel) => {
    const verdict = document.querySelector(sel.verdict);
    const views = document.querySelector(sel.views);
    return {
      verdict: verdict ? 1 : 0,
      verdictHeight: verdict ? Math.round(verdict.getBoundingClientRect().height) : 0,
      viewsTop: views ? Math.round(views.getBoundingClientRect().top) : -1,
      rows: document.querySelectorAll(sel.row).length,
    };
  }, SEL);
}

const opacityOf = (page: Page, selector: string): Promise<number> =>
  page.locator(selector).evaluate((el) => Number(getComputedStyle(el).opacity));

test("switching time window holds the routes view still instead of blanking it", async ({
  page,
}) => {
  const metrics = new MetricsPage(page);
  await page.setViewportSize({ width: 1400, height: 1000 });
  await page.goto("/#/");
  await metrics.goto();
  await metrics.selectRoute(await metrics.firstRouteLabel());

  const before = await shoot(page);
  expect(before.rows).toBeGreaterThan(0);
  expect(before.verdict).toBe(1);

  const hold = await holdMetricsRequests(page);
  await page.getByRole("button", { name: "1h", exact: true }).click();
  await hold.started;
  await settleFrames(page);

  const during = await shoot(page);
  expect(during.verdict).toBe(1);
  expect(during.verdictHeight).toBe(before.verdictHeight);
  expect(during.rows).toBeGreaterThan(0);
  expect(during.viewsTop).toBe(before.viewsTop);

  // Held-over numbers are dimmed rather than passed off as current.
  //
  // Polled, unlike the discrete reads above, because opacity is ANIMATED:
  // `.metrics-stale` transitions over 120ms, and a single read two frames
  // after the class lands can still catch the start value. Measured: passes
  // alone, fails inside a full `make check` run.
  //
  // Retrying is sound HERE and was not sound for the count in the second
  // test — the difference is the hold. While the request is parked, "is it
  // dimmed" is a state that persists, so a poll converges on the truth; a
  // poll against a 251ms absence merely outlasts it. Poll an animated value
  // whose end state is pinned; read a discrete one once.
  await expect.poll(() => opacityOf(page, SEL.verdict)).toBeLessThan(1);

  hold.release();
  // And back to full strength once the new data lands.
  await expect.poll(() => opacityOf(page, SEL.verdict)).toBe(1);
});

test("switching time window keeps the Requests count on screen", async ({ page }) => {
  const metrics = new MetricsPage(page);
  await page.setViewportSize({ width: 1400, height: 1000 });
  await page.goto("/#/");
  await metrics.goto();
  await metrics.openRequests();

  const count = page.locator(SEL.ledgerCount);
  await expect(count).toHaveCount(1);

  const hold = await holdMetricsRequests(page);
  await page.getByRole("button", { name: "1h", exact: true }).click();
  await hold.started;
  await settleFrames(page);

  // `locator.count()`, NOT `expect(...).toHaveCount(1)`. The matcher RETRIES
  // until its timeout, so against the broken build it simply waited out the
  // 251ms absence and passed — a transient defect cannot be caught by an
  // assertion that waits for it to stop happening. Same trap as `isVisible()`
  // reporting an element 6,600px below the fold as visible.
  expect(await count.count()).toBe(1);
  // Animated; see the note in the first test on why polling is sound here.
  await expect.poll(() => opacityOf(page, SEL.ledgerCount)).toBeLessThan(1);

  hold.release();
  await expect.poll(() => opacityOf(page, SEL.ledgerCount)).toBe(1);
});
