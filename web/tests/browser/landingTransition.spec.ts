import type { Page } from "@playwright/test";
import { test, expect } from "./fixtures";

// The landing → chat transition and the layout it lands in. `/api/chat` is
// routed per test: left pending by default, so the thread stays in its
// "thinking" state and nothing the server says can move the layout.

const QUESTION = "What does Hegel mean by the owl of Minerva?";

test.use({ viewport: { width: 1440, height: 900 } });

/** Leaves `/api/chat` pending, so the thread stays in "thinking". */
async function holdChat(page: Page) {
  await page.route("**/api/chat", () => {
    // Never fulfilled, on purpose.
  });
}

async function askFromLanding(page: Page, question = QUESTION) {
  await page.goto("/");
  const box = page.getByPlaceholder("What would you like to consider?");
  await box.fill(question);
  await box.press("Enter");
}

async function expectTurnAlignedWithComposer(page: Page) {
  const inner = await page.locator(".turn-user-inner").boundingBox();
  const composer = await page.locator(".composer").boundingBox();
  if (!inner || !composer) throw new Error("turn or composer has no box");
  expect(Math.abs(inner.x - composer.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(inner.width - composer.width)).toBeLessThanOrEqual(1);
}

test("user turn lines up with the composer", async ({ page }) => {
  await holdChat(page);
  await askFromLanding(page);

  const body = page.locator(".turn-user-inner .turn-body");
  await expect(body).toBeVisible();
  await expect(body).toHaveText(QUESTION);
  await expectTurnAlignedWithComposer(page);
});

test("user turn still lines up once the page scrolls", async ({ page }) => {
  // Long enough to overflow the viewport. The document is the scroller
  // (#851), and `html` reserves its gutter (`scrollbar-gutter: stable`), so a
  // scrollbar must shift the thread and the composer alike.
  const long = Array.from({ length: 1500 }, (_, i) => `word${i}`).join(" ");
  await holdChat(page);
  await askFromLanding(page, long);

  await expect(page.locator(".turn-user-inner .turn-body")).toBeVisible();
  const overflows = await page.evaluate(
    () => document.documentElement.scrollHeight > document.documentElement.clientHeight,
  );
  expect(overflows).toBe(true);
  await expectTurnAlignedWithComposer(page);
});
