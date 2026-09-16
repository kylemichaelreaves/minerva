import { test, expect } from "./fixtures";

test("the built bundle is served and the app boots", async ({ page }) => {
  const response = await page.goto("/");

  // Guards the failure this suite exists to make visible: before this
  // change CI ran `minerva serve --static web/dist` without ever building
  // web/dist, so `/` returned a 404 JSON body and nothing noticed, because
  // no test requested `/` (#593).
  expect(response?.status()).toBe(200);

  // Solid has mounted, not merely served HTML. `<main>` (App.tsx:177) only
  // exists once the app actually renders — unlike `#root` (index.html),
  // which is present in the served HTML whether or not the bundle ran.
  await expect(page.getByRole("main")).toBeVisible();
});
