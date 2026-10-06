import { describe, expect, it } from "vitest";
import { selectArcPairs } from "~/Network/components/ArcPanel";
import type { AuthorPair } from "~/api/networkApi";

const pair = (src: string, tgt: string, n: number): AuthorPair => ({
  src,
  tgt,
  n,
  intra_scrip: false,
});

/** Every name these tests use, resolved to a stand-in year. */
const ENDS = new Map(["A", "B", "C", "D", "X", "Y"].map((name, i) => [name, i * 100]));

describe("selectArcPairs", () => {
  it("dedupes by src/tgt", () => {
    const primary = [pair("A", "B", 10)];
    const supplemental = [pair("A", "B", 5), pair("C", "D", 3)];
    const out = selectArcPairs(primary, supplemental, ENDS);
    expect(out.map((e) => e.pair)).toEqual([primary[0], supplemental[1]]);
  });

  it("respects cap", () => {
    const out = selectArcPairs([pair("A", "B", 1), pair("C", "D", 2)], [], ENDS, { cap: 1 });
    expect(out).toHaveLength(1);
  });

  // #692: the name filter and the endpoint lookup are one step, so no caller
  // can hold a pair it then fails to place — which is what left NetworkArc
  // with a null-year guard that no input could reach.
  it("resolves both ends of each pair it keeps", () => {
    const [arc] = selectArcPairs([pair("B", "D", 4)], [], ENDS);
    expect(arc).toEqual({ pair: pair("B", "D", 4), src: 100, tgt: 300 });
  });

  it("drops a pair when either end is unknown", () => {
    const out = selectArcPairs(
      [pair("Nobody", "A", 9), pair("A", "Nobody", 8), pair("A", "B", 1)],
      [],
      ENDS,
    );
    expect(out.map((e) => `${e.pair.src}→${e.pair.tgt}`)).toEqual(["A→B"]);
  });

  it("caps after dropping unknown pairs, so they never take a slot", () => {
    const out = selectArcPairs([pair("Nobody", "A", 9), pair("A", "B", 1)], [], ENDS, { cap: 1 });
    expect(out.map((e) => e.pair.src)).toEqual(["A"]);
  });
});
