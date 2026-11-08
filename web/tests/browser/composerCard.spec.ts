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

// One focus indication: the card's ring. The global `:focus-visible` rule
// would otherwise paint a square accent outline over the card's rounded border.

async function focusRingOf(page: Page, placeholder: string, card: string) {
  const box = page.getByPlaceholder(placeholder);
  // Keyboard modality, so `:focus-visible` applies as it does for real users.
  for (let i = 0; i < 40; i++) {
    if (await box.evaluate((el) => el === document.activeElement)) break;
    await page.keyboard.press("Tab");
  }
  await expect(box).toBeFocused();
  await page.waitForTimeout(250);
  const input = await box.evaluate((el) => getComputedStyle(el).outlineStyle);
  const ring = await page.locator(card).evaluate((el) => {
    const cs = getComputedStyle(el);
    const probe = document.createElement("i");
    probe.style.color = "var(--ink)";
    document.body.append(probe);
    const ink = getComputedStyle(probe).color;
    probe.remove();
    return { border: cs.borderTopColor, ink, shadow: cs.boxShadow };
  });
  return { input, ring };
}

test.describe("focus ring", () => {
  for (const theme of ["light", "dark"] as const) {
    test(`landing: only the card shows the ring (${theme})`, async ({ page }) => {
      await setTheme(page, theme);
      await holdChat(page);
      await page.goto("/");
      const { input, ring } = await focusRingOf(
        page,
        "What would you like to consider?",
        ".landing-input-wrap",
      );
      expect(input).toBe("none");
      expect(ring.border).toBe(ring.ink);
    });

    test(`chat: only the card shows the ring (${theme})`, async ({ page }) => {
      await setTheme(page, theme);
      await holdChat(page);
      await page.goto("/");
      const box = page.getByPlaceholder("What would you like to consider?");
      await box.fill(QUESTION);
      await box.press("Enter");
      await expect(page.getByPlaceholder("Continue the enquiry…")).toBeVisible();
      await expect(page.locator(".lift-ghost")).toHaveCount(0, { timeout: 3000 });
      const { input, ring } = await focusRingOf(page, "Continue the enquiry…", ".composer");
      expect(input).toBe("none");
      expect(ring.border).toBe(ring.ink);
    });
  }
});

// Between the phone breakpoint and ~1064px the 280px sidebar and the
// landing's padding leave less than 720px: the card must shrink to fit.
test.describe("on a narrow desktop", () => {
  test.use({ viewport: { width: 1024, height: 768 } });

  test("the landing card stays inside the landing's column with the sidebar open", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page.locator(".sidebar")).toBeVisible();
    const card = await page.locator(".landing-input-wrap").boundingBox();
    // The landing's content box: a centred card too wide for it bleeds into
    // its 32px padding on both sides before it passes the border box.
    const landing = await page.locator(".landing").evaluate((el) => {
      const r = el.getBoundingClientRect();
      const cs = getComputedStyle(el);
      return {
        left: r.left + parseFloat(cs.paddingLeft),
        right: r.right - parseFloat(cs.paddingRight),
      };
    });
    if (!card) throw new Error("card has no box");
    expect(card.x).toBeGreaterThanOrEqual(landing.left);
    expect(card.x + card.width).toBeLessThanOrEqual(landing.right);
  });
});

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

  // "On screen" alone cannot see the phone rules: the desktop picker's
  // `max-width: 90vw`, anchored at the pill, also stays on screen (measured:
  // right edge 386 of 390, 318 of 320, 278 of 280), and only overhangs the
  // card. Inside the card is what the re-anchoring buys, so assert that too.
  for (const width of [390, 320]) {
    test(`phone: the scope picker fits on screen and inside the card at ${width}px`, async ({
      page,
    }) => {
      await page.setViewportSize({ width, height: width === 320 ? 700 : 844 });
      await phoneChat(page);
      await page.getByRole("button", { name: "Scope: All works" }).click();
      const pop = await page.locator(".chat-scope-pop").boundingBox();
      const card = await page.locator(".composer").boundingBox();
      if (!pop || !card) throw new Error("picker or card has no box");
      expect(pop.x).toBeGreaterThanOrEqual(0);
      expect(pop.x + pop.width).toBeLessThanOrEqual(width);
      expect(pop.x).toBeGreaterThanOrEqual(card.x);
      expect(pop.x + pop.width).toBeLessThanOrEqual(card.x + card.width);
    });
  }
  test("phone: the landing hint does not overlap the scope pill", async ({ page }) => {
    await holdChat(page);
    await page.goto("/");
    const pill = await page.locator(".landing-input-foot .chat-scope-control").boundingBox();
    const hint = page.locator(".landing-mobile-hint");
    const h = await hint.boundingBox();
    if (!pill || !h) throw new Error("pill or hint has no box");
    const overlaps =
      pill.x < h.x + h.width &&
      h.x < pill.x + pill.width &&
      pill.y < h.y + h.height &&
      h.y < pill.y + pill.height;
    expect(overlaps).toBe(false);
    expect(h.x).toBeGreaterThanOrEqual(pill.x + pill.width);
    // One line: truncated, not wrapped.
    expect(h.height).toBeLessThan(20);
  });
});
