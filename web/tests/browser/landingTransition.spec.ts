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

// ---------- Escape: back to the landing ----------

/** A settled one-turn chat: answered, the forward flight over. */
async function settledChat(page: Page) {
  await answerChatAtOnce(page);
  await askFromLanding(page);
  await expect(page.getByText("Dusk falls.")).toBeVisible();
  await expect(page.locator(".lift-ghost")).toHaveCount(0, { timeout: 1500 });
}

/** Runs in the page. With `when`, null until that selector matches, so the
 *  check and the read happen in one frame. */
function snapshotReturn(when: string | null) {
  if (when !== null && !document.querySelector(when)) return null;
  return {
    arriving: document.querySelectorAll(".landing.is-arriving").length,
    fading: document.querySelectorAll(".landing.is-arriving-fade").length,
    landings: document.querySelectorAll(".landing").length,
    threads: document.querySelectorAll(".thread").length,
    stage: document.documentElement.dataset.ltReturn ?? null,
    timing: document.documentElement.style.getPropertyValue("--lt-d"),
  };
}
/** Throws instead of asserting: `snapshotReturn(null)` always reads. */
function present<T>(v: T | null): T {
  if (v === null) throw new Error("no return state");
  return v;
}

/** State read once, not auto-retried: the return is transient. */
const returnState = async (page: Page) => present(await page.evaluate(snapshotReturn, null));

/** State read in the first frame `selector` matches. Waiting for the
 *  element and then reading in a second round trip raced the 180ms
 *  reduced-motion fade on CI: the class was seen, and by the read the return
 *  had finished (`stage: null`). */
async function returnStateWhen(page: Page, selector: string) {
  const handle = await page.waitForFunction(snapshotReturn, selector, {
    polling: "raf",
    timeout: 2000,
  });
  return present(await handle.jsonValue());
}

test("Escape in a settled chat returns to an empty landing", async ({ page }) => {
  await settledChat(page);
  await page.keyboard.press("Escape");

  const mid = await returnStateWhen(page, ".landing.is-arriving");
  expect(mid).toMatchObject({ arriving: 1, threads: 1, stage: "return" });

  await expect(page.locator(".thread")).toHaveCount(0, { timeout: 1500 });
  expect(await returnState(page)).toEqual({
    arriving: 0,
    fading: 0,
    landings: 1,
    threads: 0,
    stage: null,
    timing: "",
  });
  await expect(page).not.toHaveURL(/c-e2e/);
  const box = page.getByPlaceholder("What would you like to consider?");
  await expect(box).toHaveValue("");
  await expect(box).toBeFocused();
  // And it is the conversation's way out, not its end: still in the sidebar.
  await expect(page.locator(".landing")).not.toHaveClass(/fade-in/);
});

test("Escape does nothing while Minerva is considering", async ({ page }) => {
  await holdChat(page);
  await askFromLanding(page);
  await expect(page.locator(".lift-ghost")).toHaveCount(0, { timeout: 1500 });
  await expect(page.getByText("considering")).toBeVisible();

  await page.keyboard.press("Escape");
  await page.waitForTimeout(100);
  expect(await returnState(page)).toMatchObject({ landings: 0, threads: 1, stage: null });
});

test("Escape keeps a draft: it does not leave over unsent text", async ({ page }) => {
  await settledChat(page);
  await page.getByPlaceholder("Continue the enquiry…").fill("and Kant?");
  await page.keyboard.press("Escape");
  await page.waitForTimeout(100);

  expect(await returnState(page)).toMatchObject({ landings: 0, threads: 1, stage: null });
  await expect(page.getByPlaceholder("Continue the enquiry…")).toHaveValue("and Kant?");
});

test("an Escape another surface claims does not also leave", async ({ page }) => {
  await settledChat(page);
  await page.getByRole("button", { name: /scope to a work/i }).click();
  await expect(page.getByRole("listbox").or(page.getByRole("dialog")).first()).toBeVisible();

  await page.keyboard.press("Escape");
  await page.waitForTimeout(100);
  expect(await returnState(page)).toMatchObject({ landings: 0, threads: 1, stage: null });

  // The next one, with nothing open, does.
  await page.keyboard.press("Escape");
  await expect(page.locator(".thread")).toHaveCount(0, { timeout: 1500 });
});

test("from a scrolled chat the composer lands on the landing box", async ({ page }) => {
  const long = Array.from({ length: 1500 }, (_, i) => `word${i}`).join(" ");
  const sse = [
    'event: meta\ndata: {"conversation_id":"c-e2e","title":"Owl","citations":[],"abstained":false,"backend":"test"}\n\n',
    `event: delta\ndata: {"text":"${long}"}\n\n`,
    `event: done\ndata: {"response":"${long}","paragraphs":["${long}"],"dominant":"P"}\n\n`,
  ].join("");
  await page.route("**/api/chat", (route) =>
    route.fulfill({ status: 200, headers: { "content-type": "text/event-stream" }, body: sse }),
  );
  await askFromLanding(page);
  await expect(page.getByText("word1499")).toBeVisible();
  await expect(page.locator(".lift-ghost")).toHaveCount(0, { timeout: 1500 });
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  expect(await page.evaluate(() => window.scrollY)).toBeGreaterThan(0);

  await page.evaluate(() => {
    (window as unknown as { __before: Set<Animation> }).__before = new Set(
      document.getAnimations(),
    );
  });
  await page.keyboard.press("Escape");
  // Freeze in the first frame the layer exists, inside the page: a second
  // round trip could find the 650ms flight already over on a slow runner.
  await page.waitForFunction(
    () => {
      if (!document.querySelector(".landing.is-arriving")) return false;
      const before = (window as unknown as { __before: Set<Animation> }).__before;
      for (const a of document.getAnimations()) if (!before.has(a)) a.pause();
      return true;
    },
    undefined,
    { polling: "raf", timeout: 2000 },
  );

  // The flight's last frame: the composer sits on the (hidden) landing box.
  const lastFrame = await page.evaluate(() => {
    const before = (window as unknown as { __before: Set<Animation> }).__before;
    for (const a of document.getAnimations()) {
      if (before.has(a)) continue;
      a.currentTime = 650;
    }
    const c = document.querySelector(".composer")?.getBoundingClientRect();
    const b = document.querySelector(".landing-input-wrap")?.getBoundingClientRect();
    if (!c || !b) throw new Error("no composer or no landing box");
    for (const a of document.getAnimations()) if (!before.has(a)) a.play();
    return {
      c: { top: c.top, x: c.left + c.width / 2, w: c.width },
      b: { top: b.top, x: b.left + b.width / 2, w: b.width },
    };
  });
  expect(Math.abs(lastFrame.c.top - lastFrame.b.top)).toBeLessThanOrEqual(1);
  expect(Math.abs(lastFrame.c.x - lastFrame.b.x)).toBeLessThanOrEqual(1);
  expect(Math.abs(lastFrame.c.w - lastFrame.b.w)).toBeLessThanOrEqual(1);

  // …and the landing in flow puts its box exactly there: no jump on arrival.
  await expect(page.locator(".thread")).toHaveCount(0, { timeout: 1500 });
  const rest = await page.locator(".landing-input-wrap").boundingBox();
  if (!rest) throw new Error("landing box has no box");
  expect(Math.abs(rest.y - lastFrame.b.top)).toBeLessThanOrEqual(1);
  expect(Math.abs(rest.x + rest.width / 2 - lastFrame.b.x)).toBeLessThanOrEqual(1);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
});

test.describe("Escape under reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("the landing fades in and nothing travels", async ({ page }) => {
    await settledChat(page);
    // The forward crossfade has no ghost to wait out; an Escape during it
    // is ignored, so let it finish.
    await expect(page.locator(".landing")).toHaveCount(0, { timeout: 600 });
    await page.keyboard.press("Escape");
    const mid = await returnStateWhen(page, ".landing.is-arriving-fade");
    expect(mid).toMatchObject({ arriving: 0, fading: 1, stage: "fade" });

    await expect(page.locator(".thread")).toHaveCount(0, { timeout: 600 });
    await expect(page.getByPlaceholder("What would you like to consider?")).toBeFocused();
  });
});

test("picking a conversation mid-return goes there, not to the landing", async ({ page }) => {
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
  await settledChat(page);
  await page.keyboard.press("Escape");
  await expect(page.locator(".landing.is-arriving")).toBeAttached();
  await page.getByText("Earlier enquiry").click();

  await expect(page).toHaveURL(/c-old/);
  // Read once, straight away: left alone the return would finish by itself.
  expect(await returnState(page)).toMatchObject({ arriving: 0, landings: 0, stage: null });
  await expect(page.locator(".turn-user-inner .turn-body")).toHaveText("An older question");
  // …and stays there once the cancelled flight's time is up.
  await page.waitForTimeout(900);
  await expect(page).toHaveURL(/c-old/);
  expect(await page.locator(".composer-wrap").getAttribute("inert")).toBeNull();
});
