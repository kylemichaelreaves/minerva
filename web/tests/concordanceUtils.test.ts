import { describe, expect, it } from "vitest";
import {
  abbrevWork,
  sortBucketsByOrder,
} from "~/Concordance/components/FilterRail";

describe("FilterRail helpers", () => {
  it("abbrevWork uses known map", () => {
    expect(abbrevWork("Kritik der reinen Vernunft")).toBe("KrV");
  });

  it("sortBucketsByOrder preserves order", () => {
    const buckets = [
      { value: "Dat", count: 1 },
      { value: "Nom", count: 2 },
    ];
    const out = sortBucketsByOrder(buckets, ["Nom", "Dat"]);
    expect(out.map((b) => b.value)).toEqual(["Nom", "Dat"]);
  });
});
