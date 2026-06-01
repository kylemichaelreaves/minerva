import type { WordLookup } from "~/utils/types";

const POS_LABEL: Record<string, string> = {
  NOUN: "noun",
  VERB: "verb",
  ADJ: "adjective",
  ADV: "adverb",
  PRON: "pronoun",
  DET: "determiner",
  ADP: "preposition",
  CCONJ: "conj.",
  SCONJ: "conj.",
  PART: "particle",
  INTJ: "interjection",
  NUM: "numeral",
  PROPN: "proper noun",
  AUX: "auxiliary",
};
const GENDER_LABEL: Record<string, string> = {
  Masc: "masc.",
  Fem: "fem.",
  Neut: "neut.",
  Com: "common",
};
const NUMBER_LABEL: Record<string, string> = {
  Sing: "sing.",
  Plur: "plur.",
  Dual: "dual",
};

/** User-facing morph chip — "noun · masc. · sing." style. We only
 *  render the parts we have, in a canonical order, so a verb with
 *  `pos=VERB, number=Sing` shows "verb · sing." and a UD-untagged
 *  chunk (legacy `chunk_lemmas` row from before migration 0008)
 *  produces an empty string and the Show suppresses the line. */
export function formatMorphChip(info: WordLookup): string {
  const parts: string[] = [];
  if (info.pos) parts.push(POS_LABEL[info.pos] ?? info.pos.toLowerCase());
  if (info.gender) parts.push(GENDER_LABEL[info.gender] ?? info.gender.toLowerCase());
  if (info.number) parts.push(NUMBER_LABEL[info.number] ?? info.number.toLowerCase());
  return parts.join(" · ");
}
