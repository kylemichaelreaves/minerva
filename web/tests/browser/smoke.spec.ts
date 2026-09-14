import { test, expect } from "./fixtures";

test("the built bundle is served and the app boots", async ({ page }) => {
  const response = await page.goto("/");

  // Guards the failure this suite exists to make visible: before this
  // change CI ran `minerva serve --static web/dist` without ever building
  // web/dist, so `/` returned a 404 JSON body and nothing noticed, because
  // no test requested `/` (#593).
  expect(response?.status()).toBe(200);

  // Solid has mounted, not merely served HTML.
  await expect(page.locator("#root, body > div").first()).toBeVisible();
});
