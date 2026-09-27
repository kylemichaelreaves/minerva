// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseConllu } from "~/Syntax/conllu/parse";
import { arcsOf, assignLevels } from "~/Syntax/layout/arcs";
import { minimapTicks, visibleSpan } from "~/Syntax/layout/minimap";

// The whole-sentence strip. Phase 7 of docs/syntax-annotation-plan.md, and
// the last frame of the design that had no implementation.
//
// Two things can be wrong here in ways the page would not show: a tick whose
// height does not match the arc stack actually drawn over that token, and a
// viewport frame that claims to cover rows it does not.

const fixture = (name: string) => {
  const raw = readFileSync(resolve(process.cwd(), "public/data", `${name}.conllu`), "utf8");
  const sent = parseConllu(raw).sentences[0];
  if (!sent) throw new Error(`${name} parsed to no sentences`);
  return sent;
};

/** The levelled edges the diagram draws, in the same two passes it uses. */
const levelled = (tokens: Parameters<typeof arcsOf>[0]) =>
  assignLevels(arcsOf(tokens)).map(({ arc, level }) => ({
    head: arc.head,
    dep: arc.dep,
    level,
  }));

describe("minimapTicks", () => {
  it("gives every token a tick, in surface order", () => {
    const sent = fixture("fixture_projective");

    const ticks = minimapTicks(sent.tokens, levelled(sent.tokens));

    expect(ticks.map((t) => t.id)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
  });

  it("counts a token at either end of an arc, not only as the dependent", () => {
    // `entwickelt` (8) is the root and governs the level-5 `nsubj`. Counting
    // dependents only would draw it as the shallowest token in the sentence,
    // when it is exactly where the structure is deepest.
    const sent = fixture("fixture_projective");

    const ticks = minimapTicks(sent.tokens, levelled(sent.tokens));
    const byId = new Map(ticks.map((t) => [t.id, t.depth]));

    expect(byId.get(8)).toBe(5); // head of nsubj@[2,8], the tallest arc
    expect(byId.get(2)).toBe(5); // its dependent, same arc
    expect(byId.get(1)).toBe(1); // det, nothing deeper
  });

  it("floors an unattached token at one rather than at zero", () => {
    // A zero-height tick is a hole in the strip where the sentence has a
    // word, which reads as a rendering fault rather than as information.
    const ticks = minimapTicks([{ id: 1 }, { id: 2 }], [{ head: 1, dep: 2, level: 3 }]);

    expect(ticks.map((t) => t.depth)).toEqual([3, 3]);
    expect(minimapTicks([{ id: 9 }], [])[0]?.depth).toBe(1);
  });

  it("marks hand-corrected tokens", () => {
    const ticks = minimapTicks([{ id: 1, corrected: true }, { id: 2 }], []);

    expect(ticks.map((t) => t.corrected)).toEqual([true, false]);
  });
});

describe("visibleSpan", () => {
  const rows = [
    [1, 2, 3],
    [4, 5],
    [6, 7, 8, 9],
  ];

  it("spans the tokens of the one visible row", () => {
    expect(visibleSpan(rows, new Set([1]))).toEqual([3, 5]);
  });

  it("spans from the first visible row to the last", () => {
    expect(visibleSpan(rows, new Set([0, 1]))).toEqual([0, 5]);
  });

  it("covers the whole sentence when every row is on screen", () => {
    expect(visibleSpan(rows, new Set([0, 1, 2]))).toEqual([0, 9]);
  });

  it("bridges a gap rather than reporting two frames", () => {
    // Cannot happen with a scrolling pane, but a single frame from first to
    // last is the honest answer if it ever did — two frames would suggest
    // the middle row is hidden by something.
    expect(visibleSpan(rows, new Set([0, 2]))).toEqual([0, 9]);
  });

  it("reports nothing rather than everything when no row is visible", () => {
    // The pre-observation state. A frame over the whole strip here would
    // claim the opposite of what is true.
    expect(visibleSpan(rows, new Set())).toBeNull();
  });
});
