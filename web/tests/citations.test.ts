import { describe, it, expect } from "vitest";
import { splitCitations } from "~/utils/citations";

describe("splitCitations", () => {
  it("returns [] for empty / non-string input", () => {
    expect(splitCitations("")).toEqual([]);
    expect(splitCitations(null)).toEqual([]);
    expect(splitCitations(undefined)).toEqual([]);
    expect(splitCitations(42)).toEqual([]);
  });

  it("passes through plain text untouched", () => {
    expect(splitCitations("Plato says the city is the soul writ large.")).toEqual([
      "Plato says the city is the soul writ large.",
    ]);
  });

  it("extracts a single [N] marker", () => {
    expect(splitCitations("Republic 509d [1].")).toEqual([
      "Republic 509d ",
      { kind: "cite", n: 1 },
      ".",
    ]);
  });

  it("handles multiple markers including multi-digit indices", () => {
    expect(splitCitations("a [1] b [2] c [12] d")).toEqual([
      "a ",
      { kind: "cite", n: 1 },
      " b ",
      { kind: "cite", n: 2 },
      " c ",
      { kind: "cite", n: 12 },
      " d",
    ]);
  });

  it("does NOT mistake locator-style tags for citations", () => {
    // cite_style="locator" answers must round-trip the original tag as text.
    const out = splitCitations("Soul justice [Plato, Republic 441c] mirrors city.");
    expect(out).toEqual(["Soul justice [Plato, Republic 441c] mirrors city."]);
  });

  it("handles consecutive markers without surrounding text", () => {
    expect(splitCitations("[1][2]")).toEqual([
      "",
      { kind: "cite", n: 1 },
      "",
      { kind: "cite", n: 2 },
      "",
    ]);
  });
});

// `dominantFromHit` removed: the server now always supplies `dominant`,
// so there's no frontend fallback to test. See note in citations.ts.
