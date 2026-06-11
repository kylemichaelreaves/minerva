import { describe, it, expect } from "vitest";
import { renumberCitations } from "~/utils/renumber";
import type { Citation } from "~/utils/types";

function cite(n: number, extras: Partial<Citation> = {}): Citation {
  return { n, src: `s${n}`, text: `t${n}`, ...extras };
}

describe("renumberCitations()", () => {
  it("rewrites prose markers in order of first appearance", () => {
    const out = renumberCitations({
      paragraphs: ["First [3] then [1].", "And later [2] again [3]."],
      citations: [cite(1), cite(2), cite(3)],
    });
    expect(out.paragraphs).toEqual(["First [1] then [2].", "And later [3] again [1]."]);
    expect(out.citations.map((c) => c.n)).toEqual([1, 2, 3]);
    // The order in the citations array matches the new numbering.
    expect(out.citations[0]!.src).toBe("s3"); // was #3, now #1
    expect(out.citations[1]!.src).toBe("s1"); // was #1, now #2
    expect(out.citations[2]!.src).toBe("s2"); // was #2, now #3
  });

  it("leaves an already-sequential ordering untouched", () => {
    const out = renumberCitations({
      paragraphs: ["One [1] two [2] three [3]."],
      citations: [cite(1), cite(2), cite(3)],
    });
    expect(out.paragraphs).toEqual(["One [1] two [2] three [3]."]);
    expect(out.citations.map((c) => c.n)).toEqual([1, 2, 3]);
    expect(out.citations.map((c) => c.src)).toEqual(["s1", "s2", "s3"]);
  });

  it("appends uncited citations after the cited ones, preserving their original order", () => {
    const out = renumberCitations({
      paragraphs: ["Only cite [3]."],
      citations: [cite(1), cite(2), cite(3), cite(4)],
    });
    expect(out.paragraphs).toEqual(["Only cite [1]."]);
    // [3] becomes [1]; 1, 2, 4 follow in original order as 2, 3, 4.
    expect(out.citations.map((c) => c.n)).toEqual([1, 2, 3, 4]);
    expect(out.citations.map((c) => c.src)).toEqual(["s3", "s1", "s2", "s4"]);
  });

  it("handles repeated markers — only the first occurrence assigns the order", () => {
    const out = renumberCitations({
      paragraphs: ["A [2] B [2] C [1] D [2] E [1]."],
      citations: [cite(1), cite(2)],
    });
    expect(out.paragraphs).toEqual(["A [1] B [1] C [2] D [1] E [2]."]);
    expect(out.citations.map((c) => c.n)).toEqual([1, 2]);
    expect(out.citations.map((c) => c.src)).toEqual(["s2", "s1"]);
  });

  it("returns the input unchanged when citations is empty", () => {
    const input = { paragraphs: ["no cites here"], citations: [] };
    expect(renumberCitations(input)).toEqual(input);
  });

  it("returns the input unchanged when there are no prose markers", () => {
    const input = {
      paragraphs: ["no cites here at all"],
      citations: [cite(1), cite(2)],
    };
    const out = renumberCitations(input);
    // All citations are "uncited" → they keep their original order and
    // map cleanly to 1..N, which means the array is unchanged.
    expect(out.paragraphs).toEqual(["no cites here at all"]);
    expect(out.citations.map((c) => c.n)).toEqual([1, 2]);
    expect(out.citations.map((c) => c.src)).toEqual(["s1", "s2"]);
  });

  it("leaves orphan markers (referring to nonexistent citations) intact", () => {
    const out = renumberCitations({
      paragraphs: ["valid [1] orphan [9] valid [2]."],
      citations: [cite(1), cite(2)],
    });
    // [1] and [2] get renumbered as the first two seen. [9] is left
    // alone since there's no citation to map it to.
    expect(out.paragraphs).toEqual(["valid [1] orphan [9] valid [2]."]);
    expect(out.citations.map((c) => c.n)).toEqual([1, 2]);
  });

  it("matches the failing-case shape from the bug report", () => {
    // Captured from /api/conversations: prose cites in order [3,3,3,1,2,4,5,6].
    const out = renumberCitations({
      paragraphs: ["Open with [3] and [3] and [3], then [1], then [2], then [4] [5] [6]."],
      citations: [cite(1), cite(2), cite(3), cite(4), cite(5), cite(6)],
    });
    expect(out.paragraphs).toEqual([
      "Open with [1] and [1] and [1], then [2], then [3], then [4] [5] [6].",
    ]);
    expect(out.citations.map((c) => c.n)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(out.citations.map((c) => c.src)).toEqual(["s3", "s1", "s2", "s4", "s5", "s6"]);
  });

  it("preserves the `pinned` flag through the rewrite", () => {
    const out = renumberCitations({
      paragraphs: ["Cite [2] then [1]."],
      citations: [cite(1, { pinned: true }), cite(2)],
    });
    // [2] → [1], [1] → [2]. Pinned still attached to its original citation.
    expect(out.citations.find((c) => c.src === "s1")?.pinned).toBe(true);
    expect(out.citations.find((c) => c.src === "s2")?.pinned).toBeUndefined();
  });
});
