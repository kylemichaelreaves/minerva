import type { APIRequestContext } from "@playwright/test";
import { test, expect } from "./fixtures";
import { ReaderPage } from "./pages/ReaderPage";

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

  test("clicking a single word opens the rail and not the toolbar", async ({ page, request }) => {
    const reader = new ReaderPage(page);
    const { work, lang } = await firstWork(request);
    await reader.goto(work, lang);

    const line = await reader.firstPopulatedLine(4);
    await reader.clickWord(line, 0);

    await expect(reader.lookupRail).toBeVisible();
    // toBeHidden() also passes if the toolbar were deleted outright — it
    // asserts "not visible," which is true of a nonexistent element too.
    // That's fine here: the other test in this file (line 39) already
    // asserts the toolbar's positive existence and visibility, so the pair
    // together is sound. This assertion alone should not be read as proof
    // the toolbar element exists on this page.
    await expect(reader.toolbar).toBeHidden();
  });
});
