import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";
import { slugify, workKey } from "~/slug";

/** The cross-language pin (#602).
 *
 *  `web/src/slug.ts` builds the URL and `src/minerva/reader/slugs.py` resolves
 *  it, so a disagreement between them is a dead link — and one that only shows
 *  up on the works whose titles happen to contain the character they disagree
 *  about. `data/authors/work_slugs.json` is generated from the live index by
 *  `make generate-authors` and asserted from BOTH suites, so a drift fails
 *  here rather than in the address bar.
 *
 *  It is read from the committed file, never from `data/index.sqlite`: the
 *  index is gitignored, so an index-reading test passes locally and measures
 *  nothing in CI (#573). */
const FIXTURE_PATH = resolve(process.cwd(), "..", "data", "authors", "work_slugs.json");
const fixture = JSON.parse(readFileSync(FIXTURE_PATH, "utf8")) as Record<
  string,
  { author: string; title: string }
>;

test("the fixture is not empty, so an unreadable path cannot pass this file vacuously", () => {
  expect(Object.keys(fixture).length).toBeGreaterThan(800);
});

test("every committed key is what this slugifier produces for its author and title", () => {
  const mismatched = Object.entries(fixture)
    .filter(([key, { author, title }]) => workKey(author, title) !== key)
    .map(([key, { author, title }]) => `${key} != ${slugify(author)}/${slugify(title)}`);
  expect(mismatched).toEqual([]);
});
