import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "./fixtures";
import { ReaderPage } from "./pages/ReaderPage";
import { slugify } from "../../src/slug";

/** The work (and its source language) the Reader opens, derived from the
 *  running server rather than written down: which works exist — and what
 *  language they're stored in — is a property of the fixture corpus, and
 *  work titles have been renamed wholesale before (#133).
 *
 *  `lang` matters beyond identification: `work_range` (reader/queries.py)
 *  defaults a missing `lang` query param to `"grc"`, so opening a work
 *  without its actual language 404s as "no chunks for that (work, lang)"
 *  unless the work happens to have a `grc` edition. */
async function firstWork(request: APIRequestContext): Promise<{ work: string; lang: string }> {
  const res = await request.get("/api/works");
  const body = (await res.json()) as { works: { work: string; lang: string }[] };
  const first = body.works[0];
  if (!first) {
    throw new Error(
      "/api/works returned no works — the fixture index is empty. Not " +
        "skipping: the fixture is committed, so this is a real failure (#133).",
    );
  }
  if (!first.work || !first.lang) {
    // An unchecked cast on the response body turns a missing/renamed field
    // into `?lang=undefined` and an opaque `waitFor` timeout in `goto` —
    // fail loudly here instead, in the same #133 style as the empty-list
    // check above.
    throw new Error(
      `/api/works row is missing "work" or "lang": ${JSON.stringify(first)}. Not ` +
        "skipping: the fixture is committed, so this is a real failure (#133).",
    );
  }
  return { work: first.work, lang: first.lang };
}

test.describe("Reader selection", () => {
  test("a drag that ends on a word shows the selection toolbar (#591)", async ({
    page,
    request,
  }) => {
    const reader = new ReaderPage(page);
    const { work, lang } = await firstWork(request);
    await reader.goto(work, lang);

    const line = await reader.firstPopulatedLine(4);
    await reader.selectWords(line, 0, 3);

    await expect(reader.toolbar).toBeVisible();
    await expect(
      reader.toolbar.getByRole("button", { name: "Translate phrase", exact: true }),
    ).toBeVisible();
    await expect(reader.toolbar.getByRole("button", { name: "Copy", exact: true })).toBeVisible();
  });

  // The toolbar assertion above is satisfied by ANY non-empty selection, so it
  // cannot see a drag that silently starts one word late. That is the failure
  // mode #596 measured: anchoring past ~50% of a one-character word's box puts
  // the caret after the glyph, and the selection quietly omits `fromIndex`.
  test("the drag spans fromIndex in full, not the words after it (#596)", async ({
    page,
    request,
  }) => {
    const reader = new ReaderPage(page);
    const { work, lang } = await firstWork(request);
    await reader.goto(work, lang);

    const line = await reader.firstPopulatedLine(4);
    const firstWord = (await reader.words(line).nth(0).innerText()).trim();
    await reader.selectWords(line, 0, 3);

    const selection = await page.evaluate(() => window.getSelection()?.toString() ?? "");

    // One assertion, both failure modes: the dead zone yields "" and a
    // past-the-glyph anchor yields a selection starting at the SECOND word.
    expect(selection.startsWith(firstWord)).toBe(true);
  });

  test("clicking a single word opens the rail and not the toolbar", async ({ page, request }) => {
    const reader = new ReaderPage(page);
    const { work, lang } = await firstWork(request);
    await reader.goto(work, lang);

    const line = await reader.firstPopulatedLine(4);
    await reader.clickWord(line, 0);

    await expect(reader.lookupRailCloseButton).toBeVisible();
    // toBeHidden() also passes if the toolbar were deleted outright — it
    // asserts "not visible," which is true of a nonexistent element too.
    // That's fine here: the other test in this file, "a drag that ends on a
    // word shows the selection toolbar (#591)", already asserts the
    // toolbar's positive existence and visibility, so the pair together is
    // sound. This assertion alone should not be read as proof the toolbar
    // element exists on this page.
    await expect(reader.toolbar).toBeHidden();
  });
});

test.describe("readable work URLs (#602)", () => {
  /** The slug pair is resolved SERVER-side, so this is the only level at which
   *  the two slugify implementations are checked against each other through a
   *  real request. `data/authors/work_slugs.json` pins them statically; this
   *  proves the pinned algorithm is also the one the running server resolves
   *  with. jsdom cannot see it — `make check` runs neither this suite nor the
   *  e2e one (#604). */
  test("an author/title slug pair resolves against the running server", async ({
    page,
    request,
  }) => {
    const reader = new ReaderPage(page);
    const res = await request.get("/api/works");
    const body = (await res.json()) as { works: { work: string; author: string; lang: string }[] };
    const first = body.works[0];
    if (!first)
      throw new Error("/api/works returned no works — the fixture index is empty (#133).");

    await reader.gotoSlugs(slugify(first.author), slugify(first.work), first.lang);

    await expect(reader.line().first()).toBeVisible();
    // Nothing percent-encoded survives in the address bar — the point of the
    // change. `Beantwortung%20der%20Frage%3A%20Was%20ist%20Aufkl%C3%A4rung%3F`
    // is what this used to look like.
    expect(page.url()).not.toContain("%");
  });

  test("a pre-#602 bookmark rewrites itself to the slug form", async ({ page, request }) => {
    const reader = new ReaderPage(page);
    const res = await request.get("/api/works");
    const body = (await res.json()) as { works: { work: string; author: string; lang: string }[] };
    const first = body.works[0];
    if (!first)
      throw new Error("/api/works returned no works — the fixture index is empty (#133).");

    await reader.goto(first.work, first.lang);

    // `useRouting` canonicalises the hash on first load via replaceState, so
    // the old URL both resolves AND stops being the one the user copies.
    await expect(page).toHaveURL(new RegExp(`#/r/${slugify(first.work)}\\?`));
    await expect(reader.line().first()).toBeVisible();
  });
});
