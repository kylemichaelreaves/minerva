// @vitest-environment node
import { describe, expect, it } from "vitest";
import type { Arc } from "~/Syntax/layout/arcs";
import { breakRows, segmentArcs } from "~/Syntax/layout/rows";

// Wrapping is the answer to the sentence-width problem, and it is not a
// cosmetic choice. Measured on the real corpus at 20px type: the median
// German sentence is 1328px wide, 44% exceed 1440px, and the worst case is
// 7824px — 5.4 screens. Zoom-to-fit puts the median at 22px type; horizontal
// scroll means a 47-token arc is never visible as one shape. Neither lets you
// see both endpoints and the label at once, which is the whole job.
//
// So rows wrap, and arcs that cross a boundary are cut and resumed. These
// tests cover the two things that go wrong: breaking in a place that severs
// more arcs than necessary, and losing an arc when it spans a row it does not
// touch.

const tok = (i: number, form: string, upos = "NOUN") => ({ id: i, form, upos });

/** Uniform 100px tokens — width maths stays legible in the assertions. */
const widths = (n: number): number[] => Array.from({ length: n }, () => 100);

const arc = (dep: number, head: number, deprel = "dep"): Arc => ({
  head,
  dep,
  deprel,
  span: [Math.min(head, dep), Math.max(head, dep)] as const,
});

describe("breakRows", () => {
  it("keeps a sentence that fits on one row", () => {
    const toks = [tok(1, "Der"), tok(2, "Geist"), tok(3, "ist")];

    expect(breakRows(toks, widths(3), 1440)).toEqual([[1, 2, 3]]);
  });

  it("wraps when the row would overflow the measure", () => {
    // 5 tokens x 100px + 4 gaps x 18px = 572. At measure 300 only 2 fit
    // (100 + 18 + 100 = 218; a third would be 336).
    const toks = [1, 2, 3, 4, 5].map((i) => tok(i, `t${i}`));

    const rows = breakRows(toks, widths(5), 300);

    expect(rows.every((r) => r.length <= 2)).toBe(true);
    expect(rows.flat()).toEqual([1, 2, 3, 4, 5]);
  });

  it("never drops or reorders a token", () => {
    const toks = Array.from({ length: 53 }, (_, k) => tok(k + 1, `t${k + 1}`));

    const rows = breakRows(toks, widths(53), 1000);

    expect(rows.flat()).toEqual(toks.map((t) => t.id));
  });

  // The design's rule: break at punctuation in the last fifth of the measure,
  // so cuts land at clause edges where fewest arcs are severed. At realistic
  // proportions — ~78px per token against a 1440px measure — that zone is the
  // last three or four tokens of a row.
  it("prefers to break just after punctuation near the measure edge", () => {
    const toks = Array.from({ length: 20 }, (_, k) =>
      k === 10 ? tok(11, ",", "PUNCT") : tok(k + 1, `t${k + 1}`),
    );

    // 12 tokens fit (12x100 + 11x18 = 1398). The comma at index 10 lies in the
    // last fifth of that, so the break moves back to just after it.
    const rows = breakRows(toks, widths(20), 1440);

    expect(rows[0]).toHaveLength(11);
    expect(rows[0]?.at(-1)).toBe(11);
  });

  it("falls back to the hard limit when punctuation is far from the edge", () => {
    const toks = Array.from({ length: 20 }, (_, k) =>
      k === 1 ? tok(2, ",", "PUNCT") : tok(k + 1, `t${k + 1}`),
    );

    const rows = breakRows(toks, widths(20), 1440);

    // Breaking at token 2 would throw away five-sixths of the row.
    expect(rows[0]).toHaveLength(12);
  });

  it("always advances, even when one token exceeds the measure", () => {
    const toks = [tok(1, "Donaudampfschifffahrtsgesellschaft"), tok(2, "b")];

    const rows = breakRows(toks, [900, 100], 400);

    expect(rows).toEqual([[1], [2]]);
  });
});

describe("segmentArcs", () => {
  const rows = [
    [1, 2, 3],
    [4, 5, 6],
    [7, 8, 9],
  ];

  it("leaves an arc within one row whole", () => {
    const [seg] = segmentArcs([arc(1, 3, "det")], rows, false);

    expect(seg).toMatchObject({
      row: 0,
      from: 3,
      to: 1,
      cutFrom: false,
      cutTo: false,
      arrow: true,
    });
  });

  it("cuts an arc that crosses a boundary into two segments", () => {
    const segs = segmentArcs([arc(5, 2, "obj")], rows, false);

    expect(segs).toHaveLength(2);
    // Head row: runs from the head to the right edge, no arrowhead yet.
    expect(segs[0]).toMatchObject({ row: 0, from: 2, to: "R", cutTo: true, arrow: false });
    // Dependent row: resumes at the left edge and lands the arrowhead.
    expect(segs[1]).toMatchObject({ row: 1, from: "L", to: 5, cutFrom: true, arrow: true });
  });

  it("carries the partner token so a severed arc stays followable", () => {
    const segs = segmentArcs([arc(5, 2, "obj")], rows, false);

    // Reading row 0 you can see the arc continues to token 5, and vice versa.
    expect(segs[0]?.partner).toBe(5);
    expect(segs[1]?.partner).toBe(2);
  });

  it("leaves a pass-through bar on rows the arc skips entirely", () => {
    // Token 9 attaches back to token 1: three rows involved, and row 1 is
    // crossed without either endpoint being on it.
    const segs = segmentArcs([arc(9, 1, "punct")], rows, false);

    expect(segs.map((s) => s.row)).toEqual([0, 1, 2]);
    const middle = segs[1];
    expect(middle).toMatchObject({ row: 1, from: "L", to: "R", through: true });
    // A pass-through carries no arrowhead and no relation label of its own.
    expect(middle?.arrow).toBe(false);
  });

  it("orients a right-to-left arc so the cut is on the correct edge", () => {
    // Dependent precedes its head across a boundary: the dependent is on the
    // earlier row, so its segment runs to the RIGHT edge.
    const segs = segmentArcs([arc(2, 5, "nsubj")], rows, false);

    expect(segs[0]).toMatchObject({ row: 0, to: 2, arrow: true, cutFrom: true, from: "R" });
    expect(segs[1]).toMatchObject({ row: 1, from: 5, to: "L", cutTo: true, arrow: false });
  });

  it("keeps the level and label on every segment of one arc", () => {
    const a = { ...arc(9, 1, "punct"), level: 8 };

    const segs = segmentArcs([a], rows, false);

    expect(segs.every((s) => s.deprel === "punct")).toBe(true);
    expect(new Set(segs.map((s) => s.level))).toEqual(new Set([8]));
  });

  it("marks non-projective segments so they render below the row", () => {
    const segs = segmentArcs([arc(1, 3)], rows, true);

    expect(segs.every((s) => s.below)).toBe(true);
  });
});
