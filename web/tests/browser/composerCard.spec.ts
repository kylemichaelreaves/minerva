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

// ---- Phones ---------------------------------------------------------------
// The card is the same card at 390px, with 12px gutters; send shrinks to a
// 44px arrow-only circle (named by its label), and a long work title
// truncates inside the pill instead of pushing send out of the card.

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  async function phoneChat(page: Page) {
    await holdChat(page);
    await page.goto("/");
    const box = page.getByPlaceholder("What would you like to consider?");
    await box.fill(QUESTION);
    await box.press("Enter");
    await expect(page.getByPlaceholder("Reply to Minerva…")).toBeVisible();
    await expect(page.locator(".lift-ghost")).toHaveCount(0, { timeout: 3000 });
  }

  /** Scope the open chat to the fixture's longest-titled work, via the picker. */
  async function scopeToLongestTitle(page: Page): Promise<string> {
    const res = await page.request.get("/api/works");
    const { works } = (await res.json()) as { works: { display_title: string }[] };
    const longest = works.map((w) => w.display_title).sort((a, b) => b.length - a.length)[0];
    if (!longest) throw new Error("/api/works returned no works");
    await page.getByRole("button", { name: "Scope: All works" }).click();
    await page.getByPlaceholder("Filter works by title or author…").fill(longest);
    await page.locator(".chat-scope-pop__row").first().click();
    return longest;
  }

  test("phone: the card keeps its border and radius", async ({ page }) => {
    await holdChat(page);
    await page.goto("/");
    const look = await cardLook(page, ".landing-input-wrap");
    expect(look.radius).toBe("10px");
    expect(look.border).not.toBe("rgba(0, 0, 0, 0)");
    const box = await page.locator(".landing-input-wrap").boundingBox();
    expect(box?.x).toBe(12);
    // `html` reserves a scrollbar gutter, so the right edge is measured
    // against the landing's own box, not the 390px viewport.
    const landing = await page.locator(".landing").boundingBox();
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBe((landing?.x ?? 0) + (landing?.width ?? 0) - 12);

    await phoneChat(page);
    const chat = await cardLook(page, ".composer");
    expect(chat).toEqual(look);
  });

  test("phone: send is a 44px circle named by its label", async ({ page }) => {
    await phoneChat(page);
    const send = page.getByRole("button", { name: "Send" });
    const box = await send.boundingBox();
    expect(box?.width).toBe(44);
    expect(box?.height).toBe(44);
  });

  test("phone: a long work title truncates and send stays inside the card", async ({ page }) => {
    await phoneChat(page);
    const title = await scopeToLongestTitle(page);
    const work = page.locator(".composer .chat-scope__work");
    await expect(work).toHaveText(title);
    expect(await work.evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true);

    const card = await page.locator(".composer").boundingBox();
    const send = await page.locator(".composer .compose-send").boundingBox();
    if (!card || !send) throw new Error("card or send has no box");
    expect(send.x).toBeGreaterThanOrEqual(card.x);
    expect(send.x + send.width).toBeLessThanOrEqual(card.x + card.width);
  });

  test("phone: the scope picker fits on screen", async ({ page }) => {
    await phoneChat(page);
    await page.getByRole("button", { name: "Scope: All works" }).click();
    const pop = await page.locator(".chat-scope-pop").boundingBox();
    if (!pop) throw new Error("picker has no box");
    expect(pop.x).toBeGreaterThanOrEqual(0);
    expect(pop.x + pop.width).toBeLessThanOrEqual(390);
  });
});
