// Hebrew helpers for the Reader's hover-to-transliterate affordance.
// Mirror of `lib/greek.ts` for the heb-language Hebrew Masoretic Text
// chunks (OSHB / WLC). Cantillation (te'amim) and niqqud (vowel
// pointing) on the indexed chunks are dense; the romanizer strips
// cantillation and reads niqqud to produce vowels.
//
// Scheme: pragmatic, uncluttered, like the Greek romanizer.
//   - Consonants: SBL-like ASCII (b/g/d/h/v/z/kh/t/y/k/l/m/n/s/'/p/ts/q/r/sh/t)
//   - Final-form letters collapse to their non-final glyph (ך → k, ם → m, …)
//   - Shin vs Sin: distinguish via the shin-dot (ׁ) / sin-dot (ׂ); bare ש
//     defaults to "sh" (more frequent across the Tanakh).
//   - Niqqud: pataḥ/qamatz → a, segol/tsere/chataf-segol/chataf-pataḥ
//     → e/a, ḥiriq → i, ḥolam → o, qubuts/shuruq → u.
//   - Shva (ְ) is dropped pragmatically — vocalic-vs-silent shva
//     needs syllable analysis; readers add "e" mentally where needed.
//   - Dagesh (ּ) selects the "hard" form of bgdkpt (b vs v, k vs kh,
//     p vs f); for other consonants the dagesh is ignored (doubling
//     every shaddah'd consonant would clutter the tooltip).
//   - Ḥiriq + yod (ִי) → long "i" (yod silent as mater lectionis).
//   - Cantillation marks are stripped — they're recitation guides,
//     not phonemic.

// Consonants. Final forms collapse to their non-final equivalent so
// the romanizer doesn't double up. Aleph (א) and ayin (ע) are
// glottal in unpointed text; in transliteration we drop them.
const HEBREW_BASE: Record<string, string> = {
  "א": "",  // א aleph (glottal, silent)
  "ב": "b", // ב bet (dagesh selects b vs v at runtime)
  "ג": "g", // ג gimel
  "ד": "d", // ד dalet
  "ה": "h", // ה he
  "ו": "v", // ו vav (cholam/shuruq overrides at runtime)
  "ז": "z", // ז zayin
  "ח": "kh", // ח khet
  "ט": "t", // ט tet
  "י": "y", // י yod
  "ך": "kh", // ך final-kaf without dagesh
  "כ": "k", // כ kaf (dagesh selects k vs kh)
  "ל": "l", // ל lamed
  "ם": "m", // ם final-mem
  "מ": "m", // מ mem
  "ן": "n", // ן final-nun
  "נ": "n", // נ nun
  "ס": "s", // ס samekh
  "ע": "",  // ע ayin (silent)
  "ף": "f", // ף final-pe (no dagesh)
  "פ": "p", // פ pe (dagesh selects p vs f)
  "ץ": "ts", // ץ final-tsade
  "צ": "ts", // צ tsade
  "ק": "q", // ק qof
  "ר": "r", // ר resh
  "ש": "sh", // ש shin (default; sin-dot vs shin-dot overrides)
  "ת": "t", // ת tav
};

const NIQQUD: Record<string, string> = {
  "ְ": "",  // shva (silent in practice; vocalic-shva needs syllable analysis)
  "ֱ": "e", // chataf segol
  "ֲ": "a", // chataf pataḥ
  "ֳ": "o", // chataf qamatz
  "ִ": "i", // ḥiriq
  "ֵ": "e", // tsere
  "ֶ": "e", // segol
  "ַ": "a", // pataḥ
  "ָ": "a", // qamatz
  "ֹ": "o", // ḥolam
  "ֺ": "o", // ḥolam haser for vav
  "ֻ": "u", // qubuts
  "ׇ": "o", // qamatz qatan
};

const DAGESH = "ּ";
const SIN_DOT = "ׂ";
const HOLAM = "ֹ";
const HOLAM_VAV = "ֺ";
const HIRIQ = "ִ";
const VAV = "ו";
const YOD = "י";

// Cantillation marks (te'amim) and other non-niqqud marks to strip
// before the consonant walk. The two ranges we keep are the niqqud
// (U+05B0..U+05BC, vowels + dagesh) and the shin/sin dots
// (U+05C1..U+05C2). Everything else in the Hebrew block that's a
// combining mark goes: cantillation proper (U+0591..U+05AF), meteg
// (U+05BD), rafe (U+05BF), paseq (U+05C0), sof pasuq + annotations
// (U+05C3..U+05C6). Maqqef (U+05BE) is a connector, not a combining
// mark, but it's word-internal punctuation we don't want to render.
const CANTILLATION_RE = /[֑-ֽ֯-׀׃-׆]/gu;
const COMBINING_RE = /\p{M}/u;

/** Romanize one Hebrew word into pragmatic ASCII Latin.
 *
 * NFD decomposes combining niqqud / shin-dot / dagesh into separate
 * code points. We walk the BASE letters left-to-right; after each
 * letter we gather the cluster of following combining marks
 * (regardless of internal order — Unicode allows shva-then-dagesh
 * and dagesh-then-shva; OSHB ships both) and dispatch on the SET
 * of marks rather than on their position. */
export function romanize(word: string): string {
  if (!word) return word;

  const nfd = word.normalize("NFD").replace(CANTILLATION_RE, "");
  let out = "";
  let i = 0;

  while (i < nfd.length) {
    const ch = nfd[i];
    if (ch === undefined) break;

    // Gather the combining-marks cluster after this base char.
    let j = i + 1;
    const marks = new Set<string>();
    for (;;) {
      const m = nfd[j];
      if (m === undefined || !COMBINING_RE.test(m)) break;
      marks.add(m);
      j += 1;
    }

    const hasDagesh = marks.has(DAGESH);
    const hasSinDot = marks.has(SIN_DOT);

    // Step 1 — consonant.
    if (ch === VAV) {
      // vav-with-cholam → "o"; vav-with-dagesh (shuruq) → "u";
      // otherwise bare "v".
      if (marks.has(HOLAM) || marks.has(HOLAM_VAV)) {
        out += "o";
        i = j;
        continue;
      }
      if (hasDagesh) {
        out += "u";
        i = j;
        continue;
      }
      out += "v";
    } else if (ch === "ש") {
      out += hasSinDot ? "s" : "sh";
    } else if (ch === "ב") {
      out += hasDagesh ? "b" : "v";
    } else if (ch === "כ") {
      out += hasDagesh ? "k" : "kh";
    } else if (ch === "פ") {
      out += hasDagesh ? "p" : "f";
    } else if (ch in HEBREW_BASE) {
      out += HEBREW_BASE[ch] ?? "";
    } else {
      // Punctuation, ASCII, unknown — pass through.
      out += ch;
      i = j;
      continue;
    }

    // Step 2 — vowels from the niqqud cluster.
    for (const m of marks) {
      const v = NIQQUD[m];
      if (v !== undefined) out += v;
    }

    // Step 3 — ḥiriq + yod ligature: when this consonant carries
    // a ḥiriq AND the next base letter is yod with no vowel of its
    // own, the yod is mater lectionis (silent). Skip it.
    if (marks.has(HIRIQ) && nfd[j] === YOD) {
      let k = j + 1;
      const yodMarks = new Set<string>();
      for (;;) {
        const m = nfd[k];
        if (m === undefined || !COMBINING_RE.test(m)) break;
        yodMarks.add(m);
        k += 1;
      }
      const yodHasVowel = Array.from(yodMarks).some((m) => m in NIQQUD);
      if (!yodHasVowel) {
        i = k;
        continue;
      }
    }

    i = j;
  }

  return out;
}

// Hebrew + Hebrew-points ranges.
//   U+0590–U+05FF  Hebrew + Hebrew-extended (letters + points)
//
// No `\p{M}` arm (#367). This regex has one consumer — the detector
// below — and there "has a combining mark" is not "is Hebrew": with it,
// decomposed Latin and decomposed Greek both read as Hebrew. Nothing
// is lost by dropping it, because Hebrew points carry Script=Hebrew
// themselves (unlike Greek accents and Arabic harakat, which are
// Script=Inherited), so pointed text still matches on its own marks.
const HEBREW_RE = /\p{Script=Hebrew}/u;

/** Quick sniff for the Reader: only wrap words when the chunk
 *  actually contains Hebrew script. */
export function containsHebrew(text: string): boolean {
  return HEBREW_RE.test(text);
}
