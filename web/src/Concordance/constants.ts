import type { BreakdownBucket } from "~/api/concordanceApi";

export const AZ = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

// The 24 Greek capitals, alpha → omega. Drives the F1 letter rail when
// the concordance language is Ancient Greek (``grc``). Lemmas are folded
// onto these bases (see ``foldInitial``) so a single Α button matches
// ἀ/ἄ/Ἀ/α etc.
export const GREEK_AZ = "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ".split("");

/** The letter rail for a concordance language. Greek gets Α–Ω; every
 *  Latin-script language (deu/lat/eng/fra) gets A–Z. */
export function alphabetFor(lang: string): string[] {
  return lang === "grc" ? GREEK_AZ : AZ;
}

/** Fold a lemma's first character to its base capital letter — mirror of
 *  the backend ``_fold_initial`` (index_queries.py). NFD-decompose the
 *  leading code point, drop combining marks, upper-case. Maps polytonic
 *  Greek precomposed forms onto their bare capital so the rail buckets
 *  them with the plain letter: ``ἄνθρωπος`` → ``Α``, ``ὁ`` → ``Ο``. The
 *  rail's hit-set and the alpha-sort section headers both bucket on this
 *  so they agree with what the backend letter filter returns. */
export function foldInitial(lemma: string): string {
  const first = lemma[0];
  if (!first) return "";
  return first.normalize("NFD").replace(/\p{M}/gu, "").toUpperCase();
}

export const CASES_ORDER = ["Nom", "Acc", "Gen", "Dat", "Voc"];
export const NUMBERS_ORDER = ["Sing", "Plur", "Dual"];
export const GENDERS_ORDER = ["Masc", "Fem", "Neut"];

// Morphology display labels used by the concordance filter rail, KWIC
// rows and the lemma identity card. German leans on its own school
// abbreviations (Akk/Vok); Greek & Latin philology uses the Latin
// abbreviations (Acc/Voc) and carries a dual number German lacks. Kept
// here (not in a component file) so they have a single home and any
// consumer can import them without reaching into FilterRail.

const CASE_LABEL_DEU: Record<string, string> = {
  Nom: "Nom",
  Acc: "Akk",
  Gen: "Gen",
  Dat: "Dat",
  Voc: "Vok",
};

const CASE_LABEL_CLASSICAL: Record<string, string> = {
  Nom: "Nom",
  Acc: "Acc",
  Gen: "Gen",
  Dat: "Dat",
  Voc: "Voc",
};

const NUMBER_LABEL_DEU: Record<string, string> = { Sing: "Sg", Plur: "Pl" };
const NUMBER_LABEL_CLASSICAL: Record<string, string> = { Sing: "Sg", Plur: "Pl", Dual: "Du" };

/** Default German label maps are internal; use ``caseLabelFor`` /
 *  ``numberLabelFor`` in language-aware contexts. */

/** Case-abbreviation map for ``lang``. Greek/Latin get the classical
 *  Latin abbreviations; everything else falls back to the German set. */
export function caseLabelFor(lang: string): Record<string, string> {
  return lang === "grc" || lang === "lat" ? CASE_LABEL_CLASSICAL : CASE_LABEL_DEU;
}

/** Number-abbreviation map for ``lang``. Greek/Latin include the dual. */
export function numberLabelFor(lang: string): Record<string, string> {
  return lang === "grc" || lang === "lat" ? NUMBER_LABEL_CLASSICAL : NUMBER_LABEL_DEU;
}

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

/** A gender that accounts for more than this share of a lemma's
 *  attested forms is treated as *the* lemma's gender. spaCy mislabels
 *  a handful of tokens on common nouns — `ratio` comes back Fem 17,619
 *  / Masc 50 — and that long tail is noise, not evidence of a
 *  genuinely ambiguous lemma. */
export const GENDER_LOCK_THRESHOLD = 0.95;

export interface LockedGender {
  value: string;
  /** The dominant gender's share of all attested forms, 0–1. */
  share: number;
}

/** The lemma's gender when one value dominates, else null.
 *
 *  Shared by the filter rail and the lemma identity card (#507). It
 *  used to be a copy in each, and the copies disagreed: the card read
 *  the API's count-descending buckets and so took the true maximum,
 *  while the rail read them re-sorted into canonical Masc/Fem/Neut
 *  order and so scored whichever gender came *first* against the
 *  threshold. Both are handed the same object, so for about half the
 *  lemmas the card locked, the rail simultaneously showed a
 *  multi-gender chooser. **Order-independent by construction** — the
 *  maximum is taken by count, so no caller can reintroduce that by
 *  passing a differently sorted list. */
export function lockedGender(buckets: BreakdownBucket[]): LockedGender | null {
  const [first, ...rest] = buckets;
  if (first === undefined) return null;
  const top = rest.reduce((a, b) => (b.count > a.count ? b : a), first);
  if (rest.length === 0) return { value: top.value, share: 1 };
  const total = buckets.reduce((s, b) => s + b.count, 0);
  const share = top.count / total;
  return share > GENDER_LOCK_THRESHOLD ? { value: top.value, share } : null;
}

/** A locked gender's share, for the prose that reports it. "single
 *  attested" was the old wording in both components and it overstated
 *  the >95% case, which is most of them. */
export function formatGenderShare(share: number): string {
  return `${(share * 100).toFixed(share >= 0.9995 ? 0 : 1)}%`;
}
