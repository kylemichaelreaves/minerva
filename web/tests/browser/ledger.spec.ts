import { test, expect } from "./fixtures";
import { MetricsPage } from "./pages/MetricsPage";

// Enough recorded requests that the ledger cannot show them all at once.
// Without this the table is shorter than its container, `scrollHeight ===
// clientHeight`, and the assertions below pass identically whether or not
// the container can actually scroll.
const ROWS_TO_DRIVE = 30;

test("the request ledger scrolls inside the section instead of growing past it", async ({
  page,
  request,
}) => {
  for (let i = 0; i < ROWS_TO_DRIVE; i++) {
    await request.get("/api/health");
  }

  const metrics = new MetricsPage(page);
  await page.setViewportSize({ width: 1400, height: 900 });
  await metrics.goto();
  await metrics.openRequests();

  // The defect this pins: a grid item stretches to its ROW, and an implicit
  // row is `auto` — sized to content. The wrapper carried `overflow: auto`
  // the whole time and still grew to the full height of the table (measured:
  // 13,325px inside a 651px split), so the scroll never engaged and the
  // "Load older" control below it sat thousands of pixels down the document.
  const box = await metrics.ledgerScroll.evaluate((el) => ({
    client: el.clientHeight,
    scroll: el.scrollHeight,
    bottom: el.getBoundingClientRect().bottom,
  }));
  expect(box.scroll).toBeGreaterThan(box.client);

  // And it is bounded by the section rather than overflowing it. `clientHeight
  // < scrollHeight` alone would still hold for a container that overflowed the
  // panel and clipped, which is how this looked before the fix.
  const sectionBottom = await page
    .locator(".mledger-split")
    .evaluate((el) => el.getBoundingClientRect().bottom);
  expect(box.bottom).toBeLessThanOrEqual(sectionBottom + 1);

  // Fills the section it is given rather than taking a fixed slice of the
  // viewport: the first attempt at this capped it at `62vh`, which left dead
  // space on a tall window and overflowed a short one.
  const sectionHeight = await page
    .locator(".mledger-split")
    .evaluate((el) => el.getBoundingClientRect().height);
  expect(box.client).toBeGreaterThan(sectionHeight * 0.9);

  // Scrolling the container moves it — the property the two bounds above
  // exist to enable.
  await metrics.ledgerScroll.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  expect(await metrics.ledgerScroll.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
});
