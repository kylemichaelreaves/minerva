// Arabic helpers for the Reader's hover-to-transliterate affordance.
// Mirror of `utils/greek.ts` and `utils/hebrew.ts` for the ara-language
// Quran (Tanzil Uthmani) chunks. Tashkeel (fatha / kasra / damma /
// sukun / shadda) is dense on the indexed text; the romanizer reads
// the diacritics to produce vowels and to double shadda-marked
// consonants.
//
// Scheme: pragmatic ASCII, like the Greek and Hebrew romanizers.
//   - Consonants: SBL-like ASCII without macrons (b/t/th/j/h/kh/d/dh/r/z/
//     s/sh and emphatic letters folded into their plain equivalents).
//   - Tashkeel: fatha→a, kasra→i, damma→u, sukun→omit, tanwin→an/in/un.
//   - Shadda doubles the preceding consonant. Marks can appear in
//     either order in NFD (fatha-then-shadda or shadda-then-fatha),
//     so we gather the entire combining cluster after each base
//     letter and dispatch on the SET — not on positional adjacency.
//   - Alef wasla (ٱ) is silent (the connecting alef carries no
//     glottal stop at the start of the word in connected speech).
//   - Ta marbuta (ة) → "h" in pause form (the common case in cited
//     Quran prose).

const ARABIC_BASE: Record<string, string> = {
  "ا": "a",   // ا alef (carries a/ā)
  "آ": "a",   // آ alef with madda
  "أ": "a",   // أ alef with hamza above
  "إ": "i",   // إ alef with hamza below
  "ٱ": "",    // ٱ alef wasla (silent)
  "ب": "b",   // ب ba
  "ة": "h",   // ة ta marbuta (pause form)
  "ت": "t",   // ت ta
  "ث": "th",  // ث tha
  "ج": "j",   // ج jim
  "ح": "h",   // ح ḥa (folded → h)
  "خ": "kh",  // خ kha
  "د": "d",   // د dal
  "ذ": "dh",  // ذ dhal
  "ر": "r",   // ر ra
  "ز": "z",   // ز zayn
  "س": "s",   // س sin
  "ش": "sh",  // ش shin
  "ص": "s",   // ص ṣad → s
  "ض": "d",   // ض ḍad → d
  "ط": "t",   // ط ṭa → t
  "ظ": "z",   // ظ ẓa → z
  "ع": "",    // ع ayn (silent)
  "غ": "gh",  // غ ghayn
  "ف": "f",   // ف fa
  "ق": "q",   // ق qaf
  "ك": "k",   // ك kaf
  "ل": "l",   // ل lam
  "م": "m",   // م mim
  "ن": "n",   // ن nun
  "ه": "h",   // ه ha
  "و": "w",   // و waw
  "ؤ": "",    // ؤ waw with hamza above (drop)
  "ي": "y",   // ي ya
  "ى": "a",   // ى alef maksura (final ā-glide)
  "ئ": "y",   // ئ ya with hamza
  "ء": "",    // ء standalone hamza (drop)
};

// Tashkeel (combining diacritics). Maps each mark to the vowel
// fragment it contributes to the romanization. Shadda is handled
// separately because it modifies the *consonant* (doubling), not
// the syllable's vowel.
const TASHKEEL: Record<string, string> = {
  "ً": "an", // tanwin fath
  "ٍ": "in", // tanwin kasr
  "ٌ": "un", // tanwin damm
  "َ": "a",  // fatha
  "ِ": "i",  // kasra
  "ُ": "u",  // damma
  "ْ": "",   // sukun (no vowel)
  "ٰ": "a",  // dagger alef (superscript ā)
  "ٓ": "",   // madda above (lengthens the alef; "a" already emitted)
  "ٔ": "",   // hamza above (combining)
  "ٕ": "",   // hamza below (combining)
};

const SHADDA = "ّ";
const COMBINING_RE = /\p{M}/u;

/** Romanize one Arabic word into pragmatic ASCII Latin.
 *
 * NFD decomposes combining tashkeel into separate code points.
 * Different texts/editions store the same surface form with
 * different orderings of fatha+shadda etc., so we gather the entire
 * combining cluster following each base letter and dispatch on the
 * SET — emitting shadda-doubled consonants and any vowels in a
 * stable order. */
export function romanize(word: string): string {
  if (!word) return word;

  const nfd = word.normalize("NFD");
  let out = "";
  let i = 0;
  // Track the trailing vowel of the previous letter to detect
  // matres lectionis: fatha+alef = long ā (alef silent), damma+waw
  // = long ū (waw silent), kasra+ya = long ī (ya silent). Without
  // this, ``kitabun`` becomes ``kitaabun`` (double "a") because
  // both the fatha and the alef would emit "a".
  let prevVowel: "" | "a" | "i" | "u" = "";

  while (i < nfd.length) {
    const ch = nfd[i];
    if (ch === undefined) break;

    // Gather the combining-marks cluster after this base char.
    let j = i + 1;
    const marks: string[] = [];
    for (;;) {
      const m = nfd[j];
      if (m === undefined || !COMBINING_RE.test(m)) break;
      marks.push(m);
      j += 1;
    }
    const markSet = new Set(marks);

    // Mater lectionis suppression. A bare alef / waw / ya with no
    // vowel of its own, immediately after a letter that ended with
    // the matching short vowel, is the long-vowel extension — drop
    // its standalone phoneme so we don't double the vowel.
    const hasOwnVowel = marks.some((m) => m in TASHKEEL && m !== SHADDA);
    if (!hasOwnVowel) {
      if (ch === "ا" && prevVowel === "a") {
        i = j;
        continue;
      }
      if (ch === "و" && prevVowel === "u") {
        i = j;
        continue;
      }
      if (ch === "ي" && prevVowel === "i") {
        i = j;
        continue;
      }
    }

    // Base consonant lookup.
    const base = ARABIC_BASE[ch];
    if (base !== undefined) {
      // Step 1 — emit consonant (doubled if shadda is anywhere in
      // the cluster, regardless of its position relative to vowels).
      if (markSet.has(SHADDA) && base) {
        out += base + base;
      } else {
        out += base;
      }
      // Step 2 — vowels from the tashkeel cluster, in the order
      // they appear (which is canonical NFD order). Skip the
      // shadda-only entry (handled above).
      let lastVowelEmit: "" | "a" | "i" | "u" = "";
      for (const m of marks) {
        if (m === SHADDA) continue;
        const v = TASHKEEL[m];
        if (v !== undefined) {
          out += v;
          // Remember the SHORT-VOWEL CLASS of the last vowel
          // emitted. Tanwin ("an"/"in"/"un") counts for its base
          // vowel — the trailing alef after a tanwin-fath is a
          // mater lectionis just like the alef after a plain fatha.
          const first = v[0];
          if (first === "a") lastVowelEmit = "a";
          else if (first === "i") lastVowelEmit = "i";
          else if (first === "u") lastVowelEmit = "u";
        }
      }
      // If the base char itself was a vowel-letter (alef/alef-
      // variants emit "a", إ emits "i"), update prevVowel too.
      // Otherwise the consonant breaks any prior vowel chain.
      if (base === "a") prevVowel = "a";
      else if (base === "i") prevVowel = "i";
      else if (base === "u") prevVowel = "u";
      else prevVowel = lastVowelEmit;
      i = j;
      continue;
    }

    // Standalone tashkeel without an attached consonant (rare
    // edge case from leftover text-cleanup). Emit its vowel value.
    const standalone = TASHKEEL[ch];
    if (standalone !== undefined) {
      out += standalone;
      i += 1;
      continue;
    }

    // Unknown char (ASCII, punctuation, currency, …) — pass through.
    out += ch;
    prevVowel = "";
    i = j;
  }

  return out;
}

// Arabic-script ranges:
//   U+0600–U+06FF  Arabic + Arabic supplement
//   U+0750–U+077F  Arabic supplement
//   U+FB50–U+FEFF  Arabic presentation forms
//
// No `\p{M}` arm (#367). This regex has one consumer — the detector
// below — and there "has a combining mark" is not "is Arabic": with it,
// decomposed Latin and pointed Hebrew both read as Arabic. Harakat are
// Script=Inherited and so match nothing here on their own, which is
// correct: vocalized text matches on its base letters, and a bare
// fatha is no script at all.
const ARABIC_RE = /\p{Script=Arabic}/u;

/** Quick sniff for the Reader: only wrap words when the chunk
 *  actually contains Arabic script. */
export function containsArabic(text: string): boolean {
  return ARABIC_RE.test(text);
}
