import { test, expect } from "./fixtures";

// styles.css's element reset set `outline: 0` on every button, input,
// textarea and select, so a keyboard-focused control showed no ring unless its
// component happened to add a `:focus-visible` rule of its own — 29 rules for
// 131 buttons (#774). The landing page's door links ("Read", "Citations",
// "Network" in the header) are one of the many that never did: this asserts
// the global rule reaches a control with no component-level focus style.
test("a keyboard-focused button with no rule of its own shows a focus ring", async ({ page }) => {
  await page.goto("/");
  const mode = page.locator(".landing-nav__link").first();
  await expect(mode).toBeVisible();

  // Real Tab presses, not `.focus()`: `:focus-visible` is the browser's
  // keyboard-modality heuristic, and programmatic focus does not reliably
  // trigger it for a button.
  for (let i = 0; i < 40; i++) {
    await page.keyboard.press("Tab");
    if (await mode.evaluate((el) => el === document.activeElement)) break;
  }
  await expect(mode).toBeFocused();

  const outline = await mode.evaluate((el) => {
    const cs = getComputedStyle(el);
    return { style: cs.outlineStyle, width: parseFloat(cs.outlineWidth) };
  });
  expect(outline.style).not.toBe("none");
  expect(outline.width).toBeGreaterThanOrEqual(2);
});

test("a mouse click does not paint the focus ring", async ({ page }) => {
  await page.goto("/");
  const monogram = page.locator(".landing-monogram");
  await monogram.click();
  const style = await monogram.evaluate((el) => getComputedStyle(el).outlineStyle);
  expect(style).toBe("none");
});
