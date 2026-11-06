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
  // At rest: mid-flight the composer is still translated and widening.
  await expect(page.locator(".lift-ghost")).toHaveCount(0, { timeout: 1500 });
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

// ---------- The transition itself ----------

interface GhostCounter {
  __ghosts: number;
}

/** Counts every `.lift-ghost` ever inserted, so a test can tell "never
 *  appeared" from "already gone" and "flew once" from "flew twice". */
async function countGhosts(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as GhostCounter;
    w.__ghosts = 0;
    new MutationObserver((records) => {
      for (const r of records) {
        for (const n of r.addedNodes) {
          if (n instanceof HTMLElement && n.classList.contains("lift-ghost")) w.__ghosts += 1;
        }
      }
    }).observe(document, { childList: true, subtree: true });
  });
}

const ghostsInserted = (page: Page) =>
  page.evaluate(() => (window as unknown as GhostCounter).__ghosts);

/** Answers `/api/chat` immediately with a whole stream: meta (which moves
 *  the route to `#/c/c-e2e`), one delta, done. */
async function answerChatAtOnce(page: Page) {
  const sse = [
    'event: meta\ndata: {"conversation_id":"c-e2e","title":"Owl","citations":[],"abstained":false,"backend":"test"}\n\n',
    'event: delta\ndata: {"text":"Dusk falls."}\n\n',
    'event: done\ndata: {"response":"Dusk falls.","paragraphs":["Dusk falls."],"dominant":"P"}\n\n',
  ].join("");
  await page.route("**/api/chat", (route) =>
    route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: sse }),
  );
}

const liftTiming = (page: Page) =>
  page.evaluate(() => document.documentElement.style.getPropertyValue("--lt-d"));

test("Begin lifts the question into the first turn", async ({ page }) => {
  await holdChat(page);
  await askFromLanding(page);

  const ghost = page.locator(".lift-ghost");
  await expect(ghost).toHaveText(QUESTION);
  await expect(page.locator(".landing.is-leaving")).toBeAttached();
  await expect(page.getByPlaceholder("Continue the enquiry…")).toBeFocused();

  await expect(ghost).toHaveCount(0, { timeout: 1500 });
  await expect(page.locator(".landing")).toHaveCount(0);
  await expect(page.locator(".turn-user-inner .turn-body")).toBeVisible();
  await expect(page.locator(".turn-user-inner .turn-body")).toHaveText(QUESTION);
  expect(await liftTiming(page)).toBe("");
  // Focus stays in the chat composer once the landing layer goes.
  await expect(page.getByPlaceholder("Continue the enquiry…")).toBeFocused();
});

test.describe("under reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("the landing crossfades and nothing flies", async ({ page }) => {
    await countGhosts(page);
    await holdChat(page);
    await askFromLanding(page);

    await expect(page.locator(".landing")).toHaveCount(0, { timeout: 600 });
    await expect(page.locator(".turn-user-inner .turn-body")).toHaveText(QUESTION);
    expect(await ghostsInserted(page)).toBe(0);
  });
});

test("a long question flies and lands whole", async ({ page }) => {
  // Twenty lines: taller than the landing textarea's 320px, so it scrolls.
  const long = Array.from({ length: 20 }, (_, i) => `Line ${i + 1} of a long question.`).join("\n");
  await holdChat(page);
  await askFromLanding(page, long);

  const ghost = page.locator(".lift-ghost");
  expect(await ghost.textContent()).toBe(long.trim());
  await expect(ghost).toHaveCount(0, { timeout: 1500 });
  await expect(page.locator(".turn-user-inner .turn-body")).toHaveText(long);
});

test("typing straight after Enter lands in the chat composer", async ({ page }) => {
  await holdChat(page);
  await askFromLanding(page);
  await page.keyboard.type("and Kant?");

  await expect(page.locator(".lift-ghost")).toHaveCount(0, { timeout: 1500 });
  await expect(page.getByPlaceholder("Continue the enquiry…")).toHaveValue("and Kant?");
});

test("New conversation mid-flight cancels it cleanly", async ({ page }) => {
  // The server answers at once, so the route has moved to the conversation
  // and "New conversation" has somewhere to leave from. (Before the stream's
  // first event it is a no-op: #852.)
  await answerChatAtOnce(page);
  await askFromLanding(page);
  await expect(page).toHaveURL(/c-e2e/);
  await expect(page.locator(".lift-ghost")).toBeAttached();
  await page.getByRole("button", { name: "New conversation" }).click();

  // Read once, straight away (see the sidebar-pick test for why).
  const now = await page.evaluate(() => ({
    ghosts: document.querySelectorAll(".lift-ghost").length,
    leaving: document.querySelectorAll(".landing.is-leaving").length,
    timing: document.documentElement.style.getPropertyValue("--lt-d"),
  }));
  expect(now).toEqual({ ghosts: 0, leaving: 0, timing: "" });
  await expect(page.locator(".landing")).toBeVisible();
  // A fresh landing, not the one that just sent: Enter must not re-send.
  const box = page.getByPlaceholder("What would you like to consider?");
  await expect(box).toHaveValue("");
  await expect(box).toBeFocused();
});

test("picking another conversation mid-flight cancels it", async ({ page }) => {
  // One earlier conversation in the sidebar, served by stubs.
  const old = {
    id: "c-old",
    title: "Earlier enquiry",
    dominant: null,
    created_at: 1,
    updated_at: 1,
  };
  await page.route("**/api/conversations", (route) =>
    route.fulfill({ json: { conversations: [old] } }),
  );
  await page.route("**/api/conversations/c-old", (route) =>
    route.fulfill({
      json: {
        ...old,
        messages: [
          {
            role: "user",
            content: "An older question",
            created_at: 1,
            dominant: null,
            abstained: null,
            citations: [],
          },
        ],
      },
    }),
  );
  await holdChat(page);
  await askFromLanding(page);
  await expect(page.locator(".lift-ghost")).toBeAttached();
  await page.getByText("Earlier enquiry").click();

  await expect(page).toHaveURL(/c-old/);
  // Read once, straight away — not auto-retried: left alone the flight would
  // clear itself within ~850ms and a waiting assertion would pass anyway.
  const now = await page.evaluate(() => ({
    ghosts: document.querySelectorAll(".lift-ghost").length,
    landings: document.querySelectorAll(".landing").length,
    arriving: document.querySelectorAll(".thread.lt-arriving").length,
    timing: document.documentElement.style.getPropertyValue("--lt-d"),
  }));
  expect(now).toEqual({ ghosts: 0, landings: 0, arriving: 0, timing: "" });
  await expect(page.locator(".turn-user-inner .turn-body")).toHaveText("An older question");
});

test("a fast server: the reply shows mid-flight and nothing restarts", async ({ page }) => {
  await countGhosts(page);
  await answerChatAtOnce(page);
  await askFromLanding(page);

  await expect(page.getByText("Dusk falls.")).toBeVisible();
  // Still mid-flight: the reply was not held back by the animation.
  await expect(page.locator(".lift-ghost")).toHaveCount(1);
  await expect(page).toHaveURL(/c-e2e/);

  await expect(page.locator(".lift-ghost")).toHaveCount(0, { timeout: 1500 });
  expect(await ghostsInserted(page)).toBe(1);
  await expect(page.locator(".turn-user-inner .turn-body")).toHaveText(QUESTION);
});

test("a multi-line question keeps its lines on the first frame", async ({ page }) => {
  // Shift+Enter line breaks: the ghost must lay out exactly like the
  // textarea it replaces, or the question visibly reflows on frame 0.
  const lines = Array.from({ length: 6 }, (_, i) => `Line ${i + 1}`).join("\n");
  await holdChat(page);
  await page.goto("/");
  const box = page.getByPlaceholder("What would you like to consider?");
  await box.fill(lines);
  await page.evaluate(() => {
    (window as unknown as { __before: Set<Animation> }).__before = new Set(
      document.getAnimations(),
    );
  });
  await box.press("Enter");

  const heights = await page.evaluate(() => {
    const before = (window as unknown as { __before: Set<Animation> }).__before;
    for (const a of document.getAnimations()) {
      if (before.has(a)) continue;
      a.pause();
      a.currentTime = 0;
    }
    const ghost = document.querySelector<HTMLElement>(".lift-ghost");
    const ta = document.querySelector<HTMLTextAreaElement>(".landing-input");
    if (!ghost || !ta) throw new Error("no ghost or no landing textarea");
    const g = getComputedStyle(ghost);
    const t = getComputedStyle(ta);
    return {
      ghost: ghost.clientHeight - parseFloat(g.paddingTop) - parseFloat(g.paddingBottom),
      textarea: ta.scrollHeight - parseFloat(t.paddingTop) - parseFloat(t.paddingBottom),
    };
  });
  expect(Math.abs(heights.ghost - heights.textarea)).toBeLessThanOrEqual(1);
});
