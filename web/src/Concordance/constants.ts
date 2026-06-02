import type { BreakdownBucket } from "~/api/concordanceApi";

export const AZ = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

export const CASES_ORDER = ["Nom", "Acc", "Gen", "Dat", "Voc"];
export const NUMBERS_ORDER = ["Sing", "Plur"];
export const GENDERS_ORDER = ["Masc", "Fem", "Neut"];

// Morphology display labels — short German-leaning abbreviations used by
// the concordance filter rail, KWIC rows and the lemma identity card.
// Kept here (not in a component file) so they have a single home and any
// consumer can import them without reaching into FilterRail.

export const CASE_LABEL: Record<string, string> = {
  Nom: "Nom",
  Acc: "Akk",
  Gen: "Gen",
  Dat: "Dat",
  Voc: "Vok",
};

export const NUMBER_LABEL: Record<string, string> = { Sing: "Sg", Plur: "Pl" };

export const POS_LABEL: Record<string, string> = {
  NOUN: "noun",
  VERB: "verb",
  ADJ: "adj",
  ADV: "adv",
  PRON: "pron",
  ADP: "prep",
  CONJ: "conj",
  DET: "det",
  NUM: "num",
  PART: "part",
  INTJ: "intj",
  PROPN: "name",
};

export const GENDER_LABEL: Record<string, string> = {
  Masc: "masc",
  Fem: "fem",
  Neut: "neut",
};

const WORK_ABBR: Record<string, string> = {
  "Phänomenologie des Geistes": "PhdG",
  "Wissenschaft der Logik": "WL",
  "Grundlinien der Philosophie des Rechts": "GPR",
  "Enzyklopädie der philosophischen Wissenschaften im Grundrisse": "Enz",
  "Kritik der reinen Vernunft": "KrV",
  "Kritik der Urteilskraft": "KU",
  "Kritik der praktischen Vernunft": "KpV",
  "Die Metaphysik der Sitten": "MS",
  "Die Religion innerhalb der Grenzen der bloßen Vernunft": "Religion",
  "Prolegomena zu einer jeden künftigen Metaphysik": "Prol",
  "Grundlegung zur Metaphysik der Sitten": "GMS",
  "Also sprach Zarathustra": "Z",
  "Der Antichrist": "AC",
  "Zur Genealogie der Moral": "GM",
  "Jenseits von Gut und Böse": "JGB",
  "Die fröhliche Wissenschaft": "FW",
  Morgenröte: "M",
  "Götzen-Dämmerung": "GD",
  "Ecce Homo": "EH",
  "Menschliches, Allzumenschliches": "MA",
  "Aus dem Nachlaß der Achtzigerjahre": "NL",
};

export function abbrevWork(work: string): string {
  if (!work) return "—";
  if (WORK_ABBR[work]) return WORK_ABBR[work];
  const parts = work.split(/\s+/).filter((w) => /^[A-ZÄÖÜ]/.test(w));
  if (parts.length >= 2) return parts.map((p) => p[0]).join("");
  return work.slice(0, 8);
}

/** Reorder breakdown buckets to a canonical morphology order (Nom, Acc,
 *  …), appending any values not in `order` at the end in their original
 *  sequence. */
export function sortBucketsByOrder(buckets: BreakdownBucket[], order: string[]): BreakdownBucket[] {
  const known = order
    .map((k) => buckets.find((b) => b.value === k))
    .filter((b): b is BreakdownBucket => !!b);
  const unknown = buckets.filter((b) => !order.includes(b.value));
  return [...known, ...unknown];
}
