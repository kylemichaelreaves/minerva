// Diacritic folding, with no dependencies of its own.
//
// This module exists at the bottom of the import graph on purpose. `greek.ts`
// needs `stripMarks` for `romanize()`, and `searchFold.ts` needs both this and
// `greek.ts` — so the script-aware layer cannot live here without a cycle.

/** NFD-decompose and drop every combining mark.
 *
 *  **Case-preserving**, deliberately: `greek.ts`'s `romanize()` reads the first
 *  letter's case off the stripped form to keep proper nouns capitalised
 *  (`Ἀριστοτέλης` → `Aristoteles`), so lowercasing here would silently
 *  decapitalise every romanized name. Use `fold()` when you want a comparison
 *  key. */
export function stripMarks(s: string): string {
  return s.normalize("NFD").replace(/\p{M}/gu, "");
}

/** The comparison key: marks stripped and lowercased. Both normalization forms
 *  of the same word fold to the same key. */
export function fold(s: string): string {
  return stripMarks(s).toLowerCase();
}
