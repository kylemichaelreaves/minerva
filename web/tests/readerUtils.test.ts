// Tests for the pure helpers in `~/Reader/utils`. Split out from
// `useSelectionToolbar.test.ts` because `isSyntaxLangEnabled` is a
// Reader-level concern (range lang + sourceLang prop), not something the
// selection-toolbar hook computes itself — see `Reader/utils.ts`.

import { describe, expect, it } from "vitest";
import { isSyntaxLangEnabled } from "~/Reader/utils";

describe("isSyntaxLangEnabled", () => {
  it("is true for German, whichever input supplies it", () => {
    expect(isSyntaxLangEnabled("deu", undefined)).toBe(true);
    expect(isSyntaxLangEnabled(undefined, "deu")).toBe(true);
    expect(isSyntaxLangEnabled("deu", "deu")).toBe(true);
  });

  it("prefers the range's own lang over the sourceLang prop", () => {
    // The loaded range disagreeing with the route hint (e.g. right after
    // an edition switch) should defer to what's actually on screen.
    expect(isSyntaxLangEnabled("deu", "grc")).toBe(true);
    expect(isSyntaxLangEnabled("grc", "deu")).toBe(false);
  });

  it("falls back to sourceLang when the range hasn't loaded yet", () => {
    expect(isSyntaxLangEnabled(undefined, "deu")).toBe(true);
    expect(isSyntaxLangEnabled(undefined, "grc")).toBe(false);
  });

  it.each(["grc", "lat", "eng", "fra"])(
    "is false for %s from either input",
    (lang) => {
      expect(isSyntaxLangEnabled(lang, undefined)).toBe(false);
      expect(isSyntaxLangEnabled(undefined, lang)).toBe(false);
      expect(isSyntaxLangEnabled(lang, lang)).toBe(false);
    },
  );

  it("is false when both inputs are absent", () => {
    expect(isSyntaxLangEnabled(undefined, undefined)).toBe(false);
  });
});
