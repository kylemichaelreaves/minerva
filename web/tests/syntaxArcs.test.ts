import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { parseConllu } from "~/Syntax/conllu/parse";
import type { Sentence } from "~/Syntax/conllu/types";
import { apexY, arcPath, arcsOf, assignLevels, isNonProjective } from "~/Syntax/layout/arcs";

// The geometry the whole overlay rests on. Phase 1 of
// docs/syntax-annotation-plan.md ends here deliberately: if level assignment
// or non-projectivity detection is wrong, every later phase inherits it
// silently — the diagram would still render, just wrongly.
//
// Both fixtures are checked against expectations derived by hand from the
// specified algorithms, not from this implementation's output.

const fixture = (name: string): Sentence => {
  const raw = readFileSync(resolve(process.cwd(), "public/data", `${name}.conllu`), "utf8");
  const sent = parseConllu(raw).sentences[0];
  if (!sent) throw new Error(`${name} parsed to no sentences`);
  return sent;
};

/** `deprel@[i,j]=level`, sorted — a whole level assignment as one readable
 *  string, so a mismatch shows the entire shape rather than one row. */
const shape = (arcs: ReturnType<typeof assignLevels>): string[] =>
  arcs
    .map(({ arc, level }) => `${arc.deprel}@[${arc.span[0]},${arc.span[1]}]=${level}`)
    .sort((a, b) => a.localeCompare(b));

describe("arcsOf", () => {
  it("emits one arc per token, excluding the root", () => {
    const sent = fixture("fixture_projective");

    const arcs = arcsOf(sent.tokens);

    // 9 tokens, one of which (entwickelt) is the root and gets no arc.
    expect(arcs).toHaveLength(8);
    expect(arcs.some((a) => a.deprel === "root")).toBe(false);
  });

  it("spans the closed interval between head and dependent, either direction", () => {
    const sent = fixture("fixture_projective");

    const arcs = arcsOf(sent.tokens);

    // det (1 -> 2): dependent precedes its head.
    expect(arcs.find((a) => a.dep === 1)).toMatchObject({ head: 2, span: [1, 2] });
    // punct (9 -> 8): dependent follows its head.
    expect(arcs.find((a) => a.dep === 9)).toMatchObject({ head: 8, span: [8, 9] });
  });
});

describe("isNonProjective", () => {
  it("finds no crossings in the projective fixture", () => {
    const sent = fixture("fixture_projective");

    const crossing = arcsOf(sent.tokens).filter((a) => isNonProjective(a, sent.tokens));

    expect(crossing).toEqual([]);
  });

  // The brief claims only acl:relcl crosses here. It is wrong: punct (10 -> 5)
  // spans [5,10], and interior token 9 heads to 2, which is outside it. Arcs
  // 9->2 and 10->5 properly interleave (2 < 5 < 9 < 10) and would cross if
  // both were drawn above the row. See docs/syntax-annotation-plan.md.
  it("finds both crossing arcs in the non-projective fixture", () => {
    const sent = fixture("fixture_nonprojective");

    const crossing = arcsOf(sent.tokens)
      .filter((a) => isNonProjective(a, sent.tokens))
      .map((a) => `${a.deprel}@[${a.span[0]},${a.span[1]}]`);

    expect(crossing.sort()).toEqual(["acl:relcl@[2,9]", "punct@[5,10]"]);
  });

  it("treats a root-attached token inside a span as crossing it", () => {
    const sent = fixture("fixture_nonprojective");

    // acl:relcl spans [2,9]; token 5 inside it is the root (head 0), and
    // 0 < 2. head(k) === 0 satisfying `< i` is the intended reading.
    const relcl = arcsOf(sent.tokens).find((a) => a.deprel === "acl:relcl");

    expect(relcl && isNonProjective(relcl, sent.tokens)).toBe(true);
  });
});

describe("assignLevels", () => {
  // Straight from the brief, and traced by hand before implementing.
  it("matches the golden level table for the projective fixture", () => {
    const sent = fixture("fixture_projective");

    const levelled = assignLevels(arcsOf(sent.tokens));

    expect(shape(levelled)).toEqual([
      "aux@[3,8]=4",
      "case@[5,7]=2",
      "det@[1,2]=1",
      "det@[6,7]=1",
      "expl:pv@[4,8]=3",
      "nsubj@[2,8]=5",
      "obl@[7,8]=1",
      "punct@[8,9]=1",
    ]);
  });

  it("stacks the non-projective fixture's below-line arcs by containment", () => {
    const sent = fixture("fixture_nonprojective");

    const below = assignLevels(arcsOf(sent.tokens).filter((a) => isNonProjective(a, sent.tokens)));

    // punct [5,10] is narrower, so it lands first and acl:relcl [2,9] —
    // which overlaps it without containing it — is pushed to level 2.
    expect(shape(below)).toEqual(["acl:relcl@[2,9]=2", "punct@[5,10]=1"]);
  });

  it("assigns the non-projective fixture's above-line arcs", () => {
    const sent = fixture("fixture_nonprojective");

    const above = assignLevels(arcsOf(sent.tokens).filter((a) => !isNonProjective(a, sent.tokens)));

    expect(shape(above)).toEqual([
      "advmod@[8,9]=1",
      "aux@[3,5]=2",
      "det@[1,2]=1",
      "nsubj@[4,5]=1",
      "nsubj@[7,9]=2",
      "obj@[2,5]=3",
      "punct@[6,9]=3",
    ]);
  });

  it("shares a level between arcs that touch at exactly one endpoint", () => {
    // [1,2] and [2,3] abut; [1,3] contains [2,3] and must be pushed up.
    const arcs = [
      { head: 2, dep: 1, deprel: "a", span: [1, 2] as const },
      { head: 2, dep: 3, deprel: "b", span: [2, 3] as const },
      { head: 1, dep: 3, deprel: "c", span: [1, 3] as const },
    ];

    const levels = new Map(assignLevels(arcs).map(({ arc, level }) => [arc.deprel, level]));

    expect(levels.get("a")).toBe(1);
    expect(levels.get("b")).toBe(1);
    expect(levels.get("c")).toBe(2);
  });

  it("puts a nested arc below its container", () => {
    const arcs = [
      { head: 4, dep: 1, deprel: "outer", span: [1, 4] as const },
      { head: 3, dep: 2, deprel: "inner", span: [2, 3] as const },
    ];

    const levels = new Map(assignLevels(arcs).map(({ arc, level }) => [arc.deprel, level]));

    expect(levels.get("inner")).toBe(1);
    expect(levels.get("outer")).toBe(2);
  });
});

describe("arcPath", () => {
  // Flat-topped bracket with rounded corners, so the apex sits exactly on the
  // level line and label clearance is predictable. Pinned as an exact string:
  // this is a shape contract, and a stray coordinate is invisible in review.
  it("draws left-to-right above the row", () => {
    expect(arcPath(10, 100, 50, 80, 1)).toBe(
      "M 10 80 L 10 58 Q 10 50 18 50 L 92 50 Q 100 50 100 58 L 100 80",
    );
  });

  it("mirrors the corner radius below the row", () => {
    expect(arcPath(10, 100, 50, 20, -1)).toBe(
      "M 10 20 L 10 42 Q 10 50 18 50 L 92 50 Q 100 50 100 42 L 100 20",
    );
  });

  it("reverses the corner direction when the dependent precedes the head", () => {
    expect(arcPath(100, 10, 50, 80, 1)).toBe(
      "M 100 80 L 100 58 Q 100 50 92 50 L 18 50 Q 10 50 10 58 L 10 80",
    );
  });
});

describe("apexY", () => {
  it("steps upward from the row top for each level above", () => {
    expect(apexY(1, 1, 100, 140)).toBe(82); // rowTop - BASE
    expect(apexY(2, 1, 100, 140)).toBe(52); // - GAP
    expect(apexY(3, 1, 100, 140)).toBe(22);
  });

  it("mirrors downward from the row bottom for levels below", () => {
    expect(apexY(1, -1, 100, 140)).toBe(158); // rowBottom + BASE
    expect(apexY(2, -1, 100, 140)).toBe(188);
  });
});
