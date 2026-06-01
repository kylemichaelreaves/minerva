import { describe, expect, it } from "vitest";
import { selectArcPairs } from "~/Network/components/ArcPanel";
import type { AuthorPair } from "~/api/networkApi";

const pair = (src: string, tgt: string, n: number): AuthorPair => ({
  src,
  tgt,
  n,
  intra_scrip: false,
});

describe("selectArcPairs", () => {
  it("dedupes by src/tgt", () => {
    const primary = [pair("A", "B", 10)];
    const supplemental = [pair("A", "B", 5), pair("C", "D", 3)];
    const out = selectArcPairs(primary, supplemental);
    expect(out).toHaveLength(2);
    expect(out[0]?.src).toBe("A");
  });

  it("respects cap", () => {
    const out = selectArcPairs(
      [pair("A", "B", 1), pair("C", "D", 2)],
      [],
      { cap: 1 },
    );
    expect(out).toHaveLength(1);
  });

  it("filters intra-scripture when hideIntraScrip", () => {
    const intra: AuthorPair = { src: "X", tgt: "Y", n: 9, intra_scrip: true };
    const out = selectArcPairs([intra], [], { hideIntraScrip: true });
    expect(out).toHaveLength(0);
  });
});
