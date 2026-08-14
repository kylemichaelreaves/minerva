// Match-folding for type-to-filter (#363).
//
// A reader narrowing the Concordance's Work picker should not have to reproduce
// the diacritics of what they are looking for, or own a Greek keyboard. Two
// reliefs, both pinned here:
//
//   fold      — `Schroder` finds `Schröder`, `λογος` finds `λόγος`
//   romanize  — `logos` finds `λόγος`
//
// Neither is new machinery. `romanize()` already exists per script in
// `utils/greek.ts`, `utils/hebrew.ts` and `utils/arabic.ts`; `searchFold` picks
// the right one. The split into two modules is forced: `greek.ts` imports
// `stripMarks` from `fold.ts`, so the script-aware layer cannot live there
// without a cycle.

import { describe, expect, it } from "vitest";
import { fold, stripMarks } from "~/utils/fold";
import { foldForms, matchesQuery } from "~/utils/searchFold";

// Same word, both normalization forms. The NFD one is the trap: every script
// detector in the codebase answers `true` for it (#367).
const NFC_UMLAUT = "Schröder";
const NFD_UMLAUT = "Schröder";

describe("fold", () => {
  it("strips combining marks without touching case", () => {
    // Case-preserving on purpose: `greek.ts`'s `romanize()` reads the first
    // letter's case to keep proper nouns capitalised, and it calls this.
    expect(stripMarks(NFC_UMLAUT)).toBe("Schroder");
    expect(stripMarks("Ἀριστοτέλης").startsWith("Α")).toBe(true);
  });

  it("lowercases on top of the strip, for comparison", () => {
    expect(fold(NFC_UMLAUT)).toBe("schroder");
    expect(fold("λόγος")).toBe("λογος");
  });

  it("folds both normalization forms to the same key", () => {
    expect(fold(NFD_UMLAUT)).toBe(fold(NFC_UMLAUT));
  });
});

describe("foldForms", () => {
  it("offers the folded original and a romanization for Greek", () => {
    const forms = foldForms("λόγος");
    expect(forms).toContain("λογος");
    expect(forms).toContain("logos");
  });

  it("offers only the folded original for Latin text", () => {
    expect(foldForms("Republic")).toEqual(["republic"]);
  });

  it("does not mistake decomposed Latin for three different scripts", () => {
    // #367: `containsGreek` is `/[\p{Script=Greek}\p{M}]/u`, and the `\p{M}`
    // arm answers `true` for any combining mark. Measured on the exported
    // functions: NFD `Schröder` is greek=true heb=true ara=true; NFC is all
    // false. Detecting on the mark-stripped string is what makes this one
    // form instead of four junk romanizations.
    expect(foldForms(NFD_UMLAUT)).toEqual(["schroder"]);
  });

  it("romanizes Hebrew and Arabic through their own transliterators", () => {
    // Separate branches in the script dispatch; each needs its own case or
    // the branch is untested and the coverage gate is right to fail it.
    expect(foldForms("שָׁלוֹם")).toContain("shalom");
    expect(foldForms("كِتَاب")).toContain("kitab");
  });

  it("romanizes per whitespace token, so a later word keeps its breathing", () => {
    // `romanize()` is documented for a single word, and its rough-breathing
    // and initial-ρ rules are word-initial. Measured, on the real function:
    //
    //   romanize("ῥητορικῆς")      === "rhetorikes"
    //   romanize("περὶ ῥητορικῆς") === "peri retorikes"   ← the rh is lost
    //
    // A whole-string romanization silently mis-transliterates every word
    // after the first. This is the case that fails if tokens aren't split.
    expect(foldForms("περὶ ῥητορικῆς")).toContain("peri rhetorikes");
  });
});

describe("matchesQuery", () => {
  it("finds an accented Greek lemma from unaccented input", () => {
    expect(matchesQuery("λογος", ["λόγος"])).toBe(true);
  });

  it("still finds it when the reader does type the diacritics", () => {
    expect(matchesQuery("λόγος", ["λόγος"])).toBe(true);
  });

  it("finds Greek from a romanized query", () => {
    expect(matchesQuery("logos", ["λόγος"])).toBe(true);
    expect(matchesQuery("politeia", ["Πολιτεία"])).toBe(true);
  });

  it("finds a Latin diacritic from its bare form", () => {
    expect(matchesQuery("schroder", [NFC_UMLAUT])).toBe(true);
  });

  it("matches a second field, so an author's name finds their work", () => {
    // Work options carry `sublabel: w.author` (IndexPage.tsx:125). The
    // `undefined` first field is the author picker's shape (IndexPage.tsx:110).
    expect(matchesQuery("plato", [undefined, "Plato"])).toBe(true);
  });

  it("does not match a query absent from every field", () => {
    expect(matchesQuery("hegel", ["Republic", "Plato"])).toBe(false);
  });

  it("does not match the literal string 'undefined' for an absent field", () => {
    expect(matchesQuery("undefined", ["Plato", undefined])).toBe(false);
  });

  it("does not let a query span the join between two fields", () => {
    // `WorkScopeControl` concatenates `"${author} ${title}"` into one
    // haystack, which lets a query match across the join. Fields here are
    // alternatives, not a phrase.
    expect(matchesQuery("republicplato", ["Republic", "Plato"])).toBe(false);
  });

  it("treats an empty or whitespace-only query as matching everything", () => {
    expect(matchesQuery("", ["Republic"])).toBe(true);
    expect(matchesQuery("   ", ["Republic"])).toBe(true);
  });
});
