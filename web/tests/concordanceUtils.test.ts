import { describe, expect, it } from "vitest";
import type { BreakdownBucket } from "~/api/concordanceApi";
import { abbrevWork, sortBucketsByOrder } from "~/Concordance/constants";

describe("concordance constants helpers", () => {
  it("abbrevWork uses known map", () => {
    expect(abbrevWork("Kritik der reinen Vernunft")).toBe("KrV");
  });

  it("sortBucketsByOrder preserves order", () => {
    const buckets: BreakdownBucket[] = [
      { value: "Dat", count: 1 },
      { value: "Nom", count: 2 },
    ];
    const out = sortBucketsByOrder(buckets, ["Nom", "Dat"]);
    expect(out.map((b) => b.value)).toEqual(["Nom", "Dat"]);
  });
});
