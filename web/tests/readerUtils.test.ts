// Tests for the pure helpers in `~/Reader/utils`. Split out from
// `useSelectionToolbar.test.ts` because `isSyntaxLangEnabled` is a
// Reader-level concern (range lang + sourceLang prop), not something the
// selection-toolbar hook computes itself — see `Reader/utils.ts`.

import { describe, expect, it } from "vitest";
import { escapeExitsReader, isSyntaxLangEnabled } from "~/Reader/utils";

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

describe("escapeExitsReader", () => {
  // Escape is the Reader's last resort, not its first — every surface below
  // already answers it, and exiting past one of them would throw away the
  // reader the user was only trying to un-clutter (#342 made the syntax
  // overlay one of them by keeping the Reader mounted underneath it).
  const quiet = {
    rail: false,
    termCard: false,
    xrefCard: false,
    selectionToolbar: false,
    settingsSheet: false,
    syntaxLayer: false,
  };

  it("exits when every surface is closed", () => {
    expect(escapeExitsReader(quiet)).toBe(true);
  });

  for (const surface of Object.keys(quiet) as (keyof typeof quiet)[]) {
    it(`does not exit while the ${surface} is open`, () => {
      expect(escapeExitsReader({ ...quiet, [surface]: true })).toBe(false);
    });
  }
});
