/** URL slugs for reader work routes (#602).
 *
 *  This is HALF of the algorithm; the other half is
 *  `src/minerva/reader/slugs.py`. A link this file builds is resolved by that
 *  one, so any disagreement is a dead link. `data/authors/work_slugs.json` is
 *  the generated fixture that pins them together, asserted from both suites.
 */

/** NFKD decomposes an accented letter into base + combining mark, which the
 *  mark strip then removes. It does NOT touch these — they are atomic
 *  codepoints with no canonical decomposition — so without this pass they
 *  reach `[^a-z0-9]+` and are deleted rather than folded: `bloßen` would slug
 *  to `blo-en`, not `blossen`. */
const UNDECOMPOSED: readonly (readonly [string, string])[] = [
  ["ß", "ss"],
  ["æ", "ae"],
  ["Æ", "ae"],
  ["œ", "oe"],
  ["Œ", "oe"],
  ["ø", "o"],
  ["Ø", "o"],
];

/** Fold `text` to a lowercase ASCII `[a-z0-9-]` slug.
 *
 *  The steps are ordered, and the order matters: the expansions above must run
 *  BEFORE combining marks are stripped, because two of them (`ø`, `ß`) are
 *  single codepoints that NFKD leaves alone. */
export function slugify(text: string): string {
  let s = text.normalize("NFKD");
  for (const [src, dst] of UNDECOMPOSED) s = s.split(src).join(dst);
  s = s.replace(/\p{M}/gu, "");
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** The `#/r/<authorSlug>/<titleSlug>` path, without the `#/r/`.
 *
 *  Mirrors `work_key` in `src/minerva/reader/slugs.py`. Neither slug can
 *  contain `/` — the character class that survives is `[a-z0-9-]` — so the
 *  separator is unambiguous and the pair splits back apart exactly. */
export function workKey(author: string, title: string): string {
  return `${slugify(author)}/${slugify(title)}`;
}
