// The UD part-of-speech inventory the picker offers, and nothing else.
//
// Closed on purpose, for the same reason `relations.ts` is: a wrong tag
// validates, exports, and is wrong, and nothing downstream reports it. But the
// specific hazard here is sharper than a typo. The German parser carries a
// TIGER/STTS tag alongside the UD one, and the TIGER tags are shaped exactly
// like UD tags — `NN`, `NE`, `ADJA`, `PRELS`, `VVFIN`. A shape check would
// admit every one of them, so membership is the only check worth having, and
// it is duplicated on the server (`syntax/validate.py::UPOS_TAGS`).
//
// NOT reused from `~/Reader/wordInfoMorph`'s `POS_LABEL`. That map is for
// prose display and carries 14 of the 17 — it omits `PUNCT`, `SYM` and `X`.
// `PUNCT` is precisely the tag whose mis-assignment is visible in this view:
// row wrapping breaks after punctuation (`layout/rows.ts`) and the
// topological-field bands split around it (`layout/fields.ts`), so a
// picker that could not reach it would leave the one POS error that moves
// the diagram uncorrectable. See #253.
//
// Groups follow the UD taxonomy — open class, closed class, other — so the
// list reads in the order a linguist scans rather than alphabetically.

export interface PosTag {
  /** The tag as written to storage and to CoNLL-U's UPOS column. */
  name: string;
  /** One-line gloss, shown beside the name in the picker. */
  gloss: string;
}

export interface PosGroup {
  title: string;
  tags: PosTag[];
}

const g = (title: string, pairs: [string, string][]): PosGroup => ({
  title,
  tags: pairs.map(([name, gloss]) => ({ name, gloss })),
});

export const POS_GROUPS: PosGroup[] = [
  g("Open class", [
    ["NOUN", "noun"],
    ["PROPN", "proper noun"],
    ["VERB", "verb"],
    ["ADJ", "adjective"],
    ["ADV", "adverb"],
    ["INTJ", "interjection"],
  ]),
  g("Closed class", [
    ["AUX", "auxiliary or copula"],
    ["PRON", "pronoun"],
    ["DET", "determiner"],
    ["ADP", "preposition or postposition"],
    ["NUM", "numeral"],
    ["PART", "particle"],
    ["CCONJ", "coordinating conjunction"],
    ["SCONJ", "subordinating conjunction"],
  ]),
  g("Other", [
    ["PUNCT", "punctuation"],
    ["SYM", "symbol"],
    ["X", "other or unanalysable"],
  ]),
];

export const POS_TAGS: PosTag[] = POS_GROUPS.flatMap((group) => group.tags);

const BY_NAME = new Map(POS_TAGS.map((t) => [t.name, t]));

export function isKnownPos(name: string): boolean {
  return BY_NAME.has(name);
}

export function posGloss(name: string): string | undefined {
  return BY_NAME.get(name)?.gloss;
}

/**
 * The inventory filtered by a substring, keeping group order and dropping
 * groups that end up empty.
 *
 * Case-insensitive on the query but never on the stored tag: someone typing
 * "propn" should find `PROPN`, while `validateUpos("noun")` still refuses,
 * because the picker is what produces the value and it only ever emits the
 * canonical upper-case form.
 */
export function filterPos(query: string): PosGroup[] {
  const q = query.trim().toLowerCase();
  if (q === "") return POS_GROUPS;
  return POS_GROUPS.map((group) => ({
    title: group.title,
    tags: group.tags.filter(
      (t) => t.name.toLowerCase().includes(q) || t.gloss.includes(q),
    ),
  })).filter((group) => group.tags.length > 0);
}
