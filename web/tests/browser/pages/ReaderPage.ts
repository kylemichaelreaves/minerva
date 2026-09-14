import type { Locator, Page } from "@playwright/test";

/** Intent-level API for the Reader route.
 *
 *  Every accessor returns a Locator, never an ElementHandle: a Locator
 *  re-resolves on each use and carries Playwright's auto-waiting, while a
 *  handle is a snapshot that goes stale and then gets "fixed" with a sleep.
 *  Nothing here asserts — assertions belong in specs, so a failure names the
 *  behaviour that broke rather than a helper. */
export class ReaderPage {
  constructor(private readonly page: Page) {}

  /** `lang` is required in practice, not merely allowed: `work_range`
   *  (reader/queries.py) defaults an absent `lang` query param to `"grc"`
   *  regardless of what the work actually contains, so a fixture work
   *  stored only in `eng` (as this corpus's Republic/Theaetetus/
   *  Nicomachean Ethics are) 404s with "no chunks for that (work, lang)"
   *  when `lang` is omitted. The brief's `goto(workId)` signature assumed
   *  `lang` was optional; it is not, for this fixture. */
  async goto(workId: string, lang: string): Promise<void> {
    await this.page.goto(`/#/r/${encodeURIComponent(workId)}?lang=${encodeURIComponent(lang)}`);
    await this.line().first().waitFor();
  }

  /** Rendered lines. `data-chunk-id` is not a test hook: production code
   *  queries it at Reader/index.tsx:246, utils.ts:92,
   *  useSelectionToolbar.tsx:263 and useWorkRange.tsx:225. */
  line(chunkId?: string): Locator {
    return chunkId === undefined
      ? this.page.locator("[data-chunk-id]")
      : this.page.locator(`[data-chunk-id="${chunkId}"]`);
  }

  /** Words within a line, in reading order. `data-offset` is the word's
   *  character offset in the chunk — app data, not styling. */
  words(line: Locator): Locator {
    return line.locator("[data-offset]");
  }

  /** The first line carrying at least `minWords` words.
   *
   *  Derived at run time rather than hardcoded: chunk ids come from the
   *  fixture corpus and churn whenever chunking changes — dropping one
   *  paragraph renumbers every chunk after it. serve.test.ts states the same
   *  rule for work rows (#133).
   *
   *  Throws rather than skipping. The fixture is committed, so a corpus that
   *  cannot satisfy this is a real failure. */
  async firstPopulatedLine(minWords: number): Promise<Locator> {
    const lines = this.line();
    const count = await lines.count();
    for (let i = 0; i < count; i++) {
      const candidate = lines.nth(i);
      if ((await this.words(candidate).count()) >= minWords) return candidate;
    }
    throw new Error(
      `no rendered line has ${String(minWords)} words. The fixture corpus is ` +
        `committed, so this is a real failure, not an environment difference — ` +
        `not skipping (#133).`,
    );
  }

  /** Drag-select from one word to another through real input.
   *
   *  Boxes are resolved at call time, never cached. The intermediate move is
   *  required: a single move-then-up does not reliably produce a selection in
   *  Chromium. This is the whole point of the suite — the mouseup's `target`
   *  comes from hit-testing, not from the test's choice of dispatch node, which
   *  is exactly the parameter every jsdom test was blind to in #591.
   *
   *  The anchor for each endpoint is a small fixed distance inside its
   *  OUTER edge — never the geometric center. Measured against a static
   *  reproduction of this exact markup (no app JS, no CSS): starting a drag
   *  at the exact horizontal center of a narrow one-character word (e.g.
   *  "I", ~5px wide) lands in a sub-pixel dead zone where Chromium
   *  repeatedly re-collapses the selection to the current mouse position
   *  instead of extending it from the mousedown anchor — scanning
   *  fractional offsets across that word's box found the dead zone at
   *  roughly 50-55% of the width, with 25% and 75% both extending
   *  correctly. Anchoring at the outer edges rather than a tuned fraction
   *  of the center both clears that band at every width AND makes the
   *  drag actually span words `fromIndex..toIndex` in full — a fraction
   *  anywhere past 50% starts *after* a one-character `fromIndex` word,
   *  silently excluding it from the selection. */
  async selectWords(line: Locator, fromIndex: number, toIndex: number): Promise<void> {
    const words = this.words(line);
    const from = await words.nth(fromIndex).boundingBox();
    const to = await words.nth(toIndex).boundingBox();
    if (!from || !to) throw new Error("word has no box — is the line visible?");

    const startX = from.x + Math.min(2, from.width / 4);
    const startY = from.y + from.height / 2;
    const endX = to.x + to.width - Math.min(2, to.width / 4);
    const endY = to.y + to.height / 2;

    const mouse = this.page.mouse;
    await mouse.move(startX, startY);
    await mouse.down();
    await mouse.move(startX + (endX - startX) / 2, startY + (endY - startY) / 2, { steps: 8 });
    await mouse.move(endX, endY, { steps: 8 });
    await mouse.up();
  }

  /** Press and release on a single word, without dragging. */
  async clickWord(line: Locator, index: number): Promise<void> {
    const box = await this.words(line).nth(index).boundingBox();
    if (!box) throw new Error("word has no box — is the line visible?");
    const mouse = this.page.mouse;
    await mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await mouse.down();
    await mouse.up();
  }

  get toolbar(): Locator {
    return this.page.getByRole("toolbar", { name: "Selection actions", exact: true });
  }

  /** The rail is inside `<Show when={state.kind !== "idle"}>`, so presence
   *  means open. Anchored on the close control's own label. */
  get lookupRailCloseButton(): Locator {
    return this.page.getByRole("button", { name: "Close drawer", exact: true });
  }
}
