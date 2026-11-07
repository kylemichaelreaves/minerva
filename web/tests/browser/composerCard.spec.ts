import type { Page } from "@playwright/test";
import { test, expect } from "./fixtures";

// The landing card and the chat card are one component in two sizes: they
// share radius, background and border, and differ only in resting height.

const QUESTION = "What does Hegel mean by the owl of Minerva?";

test.use({ viewport: { width: 1280, height: 800 } });

async function holdChat(page: Page) {
  await page.route("**/api/chat", () => {
    // Never fulfilled, on purpose: the thread stays in "thinking".
  });
}

/** Read at rest: the focus ring recolours the border (and transitions), so
 *  blur first and wait out the transition. */
async function cardLook(page: Page, selector: string) {
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.waitForTimeout(250);
  return page.locator(selector).evaluate((el) => {
    const cs = getComputedStyle(el);
    return {
      radius: cs.borderTopLeftRadius,
      background: cs.backgroundColor,
      border: cs.borderTopColor,
    };
  });
}

async function setTheme(page: Page, theme: "light" | "dark") {
  await page.addInitScript((t) => {
    document.documentElement.setAttribute("data-theme", t);
  }, theme);
}

for (const theme of ["light", "dark"] as const) {
  test.describe(`${theme} theme`, () => {
    test.beforeEach(async ({ page }) => {
      await setTheme(page, theme);
      await holdChat(page);
      await page.goto("/");
      await page.evaluate((t) => document.documentElement.setAttribute("data-theme", t), theme);
    });

    async function beginQuestion(page: Page) {
      const box = page.getByPlaceholder("What would you like to consider?");
      await box.fill(QUESTION);
      await box.press("Enter");
      await expect(page.getByPlaceholder("Continue the enquiry…")).toBeVisible();
      await expect(page.locator(".lift-ghost")).toHaveCount(0, { timeout: 3000 });
    }

    test("landing and chat cards share radius, background and border", async ({ page }) => {
      const landing = await cardLook(page, ".landing-input-wrap");
      await beginQuestion(page);
      const chat = await cardLook(page, ".composer");
      expect(chat).toEqual(landing);
      expect(landing.radius).toBe("10px");
    });

    test("send is a filled accent pill", async ({ page }) => {
      const accent = await page.evaluate(() => {
        const probe = document.createElement("i");
        probe.style.backgroundColor = "var(--accent)";
        document.body.append(probe);
        const c = getComputedStyle(probe).backgroundColor;
        probe.remove();
        return c;
      });
      const send = page.locator(".compose-send");
      await page.getByPlaceholder("What would you like to consider?").fill("x");
      await expect(send).toHaveCSS("background-color", accent);
      expect((await send.boundingBox())?.height).toBe(40);
    });

    test("rests at three lines on the landing and two in the chat", async ({ page }) => {
      const landingH = await page.locator(".landing-input").evaluate((el) => el.clientHeight);
      expect(landingH).toBeGreaterThanOrEqual(104);
      await beginQuestion(page);
      const chatH = await page.locator(".composer-input").evaluate((el) => el.clientHeight);
      expect(chatH).toBeGreaterThanOrEqual(64);
    });
  });
}
