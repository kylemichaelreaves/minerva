// Polytonic Greek helpers for the Reader's hover-to-transliterate
// affordance. The server already converts Perseus beta-code to
// polytonic Unicode (see `src/minerva/transliterate.py`); this module
// goes the other direction — Greek → Latin romanization — for tooltip
// text shown next to a hovered word.
//
// Scheme: pragmatic ASCII classical.
//   - η → e, ω → o (no macrons; we want tooltips uncluttered)
//   - Rough breathing on a vowel → leading "h"
//   - Initial ρ with rough breathing → "rh"
//   - γ before γ/κ/ξ/χ → "n" (e.g. ἄγγελος → angelos)
//   - υ → y standalone, "u" as the second member of a diphthong
//     (αυ/ευ/ηυ/ου/ωυ)
//   - θ/φ/χ/ψ/ξ → th/ph/ch/ps/x
//   - Other accents and iota subscript dropped
//
// If a scheme with macrons or strict ALA-LC is wanted later, swap the
// table below; the tokenizer and Reader integration stay the same.

const GREEK_BASE: Record<string, string> = {
  α: "a",
  β: "b",
  γ: "g",
  δ: "d",
  ε: "e",
  ζ: "z",
  η: "e",
  θ: "th",
  ι: "i",
  κ: "k",
  λ: "l",
  μ: "m",
  ν: "n",
  ξ: "x",
  ο: "o",
  π: "p",
  ρ: "r",
  σ: "s",
  ς: "s",
  τ: "t",
  // υ is contextual — see the diphthong rule in `romanize`. The table
  // value here is the standalone (non-diphthong) form.
  υ: "y",
  φ: "ph",
  χ: "ch",
  ψ: "ps",
  ω: "o",
};

// All regex literals here use \u escapes rather than literal
// combining marks — eslint's `no-misleading-character-class` rule
// flags unattached marks in character classes (they look like they
// belong to the preceding bracket), and editors render the orphans
// confusingly. Ranges in use:
//   U+0300–U+036F  general combining diacritics (accents/breathings)
//   U+0345         combining ypogegrammeni (iota subscript)
//   U+0314         combining rough breathing (subset of the above)
const DIACRITIC_RE = /\p{M}/gu;
const ROUGH_BREATHING = "\u0314";

function stripDiacritics(s: string): string {
  return s.normalize("NFD").replace(DIACRITIC_RE, "");
}

// Combining rough breathing = U+0314. Its presence anywhere in the
// NFD form means the word starts with an aspirated vowel (or initial ρ).
function hasRoughBreathing(word: string): boolean {
  return word.normalize("NFD").includes(ROUGH_BREATHING);
}

export function romanize(word: string): string {
  if (!word) return word;
  const rough = hasRoughBreathing(word);
  const stripped = stripDiacritics(word);
  let out = "";
  for (let i = 0; i < stripped.length; i++) {
    const raw = stripped[i];
    if (raw === undefined) continue;
    const ch = raw.toLowerCase();
    // γ-nasal rule: γ before γ/κ/ξ/χ surfaces as 'n' (Liddell-Scott
    // convention, e.g. ἄγγελος → angelos, not aggelos).
    if (ch === "γ" && i + 1 < stripped.length) {
      const next = stripped[i + 1]?.toLowerCase();
      if (next === "γ" || next === "κ" || next === "ξ" || next === "χ") {
        out += "n";
        continue;
      }
    }
    // Initial ρ with rough breathing → 'rh' (e.g. ῥήτωρ → rhetor).
    if (ch === "ρ" && i === 0 && rough) {
      out += "rh";
      continue;
    }
    // Diphthong υ: when υ follows a back vowel (αυ, ευ, ηυ, ου, ωυ)
    // it's the diphthong's second element and is rendered 'u' rather
    // than the standalone 'y'. Checking the previous stripped char
    // (already accent-free) is enough — diacritics never sit between
    // the two vowels of a diphthong in NFC, and we're past NFD strip.
    if (ch === "υ" && i > 0) {
      const prev = stripped[i - 1]?.toLowerCase();
      if (prev === "α" || prev === "ε" || prev === "η" || prev === "ο" || prev === "ω") {
        out += "u";
        continue;
      }
    }
    out += GREEK_BASE[ch] ?? raw;
  }
  // Diphthongs (αυ, ευ) don't get an aspirated 'h' wedged in front;
  // we only prepend 'h' when the word actually starts on a vowel and
  // the breathing is rough. The check looks at the *romanized*
  // output's first letter since by then γ-nasal and rh have already
  // been resolved.
  if (rough && /^[aeiou]/i.test(out)) {
    out = "h" + out;
  }
  // Preserve initial capitalization from the source word so proper
  // nouns (Ἀριστοτέλης → Aristoteles) keep their cap.
  const first = stripped.at(0);
  if (first !== undefined && first !== first.toLowerCase()) {
    out = out.charAt(0).toUpperCase() + out.slice(1);
  }
  return out;
}

// Greek + Greek-Extended + combining-mark ranges. Anything else
// (whitespace, punctuation, Latin) is treated as a non-word run.
//   U+0370–U+03FF  Greek and Coptic
//   U+1F00–U+1FFF  Greek Extended (precomposed polytonic glyphs)
//   U+0300–U+036F + U+0345  combining accents/breathings/iota sub
// `\p{Script=Greek}` matches Greek/Coptic + Greek-Extended letters but
// not combining marks (those carry Script=Inherited); union with
// `\p{M}` to keep accents/breathings attached to their word run.
const GREEK_RE = /[\p{Script=Greek}\p{M}]/u;
const TOKEN_RE = /[\p{Script=Greek}\p{M}]+|[^\p{Script=Greek}\p{M}]+/gu;

// Language-agnostic word/non-word split. `\p{L}` covers Latin, Greek,
// Cyrillic, Hebrew, Arabic, …; including `\p{M}` keeps combining
// marks attached to their host letter rather than splitting them
// into their own run.
const ANY_LETTER_RE = /[\p{L}\p{M}]/u;
const ANY_TOKEN_RE = /[\p{L}\p{M}]+|[^\p{L}\p{M}]+/gu;

export interface GreekToken {
  /** True iff this run is a word (any letter script). False for
   *  whitespace + punctuation runs. */
  word: boolean;
  s: string;
  /** Character offset where this run starts in the input string.
   *  Used by the Reader to map a word against term-occurrence spans
   *  whose offsets are anchored to the same chunk text. */
  offset: number;
}

export function tokenizeGreek(text: string): GreekToken[] {
  const out: GreekToken[] = [];
  for (const m of text.matchAll(TOKEN_RE)) {
    const s = m[0];
    // matchAll always populates `index` (TS still types it as
    // possibly-undefined in older targets but our config narrows it).
    out.push({ word: GREEK_RE.test(s), s, offset: m.index });
  }
  return out;
}

/** Tokenise any-script source text into alternating word / non-word
 *  runs. Used by the Reader to render per-word `.gw` hover affordance
 *  on German (and any future non-Greek source language) without
 *  language-specific tokenisation. Greek still routes through
 *  `tokenizeGreek` so its tighter Script=Greek regex catches the
 *  combining-mark interaction with breathings + accents. */
export function tokenizeWords(text: string): GreekToken[] {
  const out: GreekToken[] = [];
  for (const m of text.matchAll(ANY_TOKEN_RE)) {
    out.push({ word: ANY_LETTER_RE.test(m[0]), s: m[0], offset: m.index });
  }
  return out;
}

// Quick sniff for the Reader: only wrap words when the chunk actually
// contains Greek script. Cheap enough to call per chunk.
export function containsGreek(text: string): boolean {
  return GREEK_RE.test(text);
}
