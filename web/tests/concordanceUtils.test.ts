import { describe, expect, it } from "vitest";
import type { BreakdownBucket } from "~/api/concordanceApi";
import {
  abbrevWork,
  alphabetFor,
  AZ,
  caseLabelFor,
  foldInitial,
  GREEK_AZ,
  numberLabelFor,
  sortBucketsByOrder,
} from "~/Concordance/constants";

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

describe("foldInitial", () => {
  it("folds polytonic Greek precomposed forms onto their base capital", () => {
    expect(foldInitial("ἄνθρωπος")).toBe("Α"); // smooth + acute
    expect(foldInitial("ἀγαθός")).toBe("Α"); // smooth breathing
    expect(foldInitial("Ἀθηνᾶ")).toBe("Α"); // capital + smooth
    expect(foldInitial("α")).toBe("Α"); // bare lowercase
    expect(foldInitial("ὁ")).toBe("Ο"); // omicron + rough
    expect(foldInitial("λόγος")).toBe("Λ"); // lambda — distinct bucket
  });

  it("upper-cases plain Latin-script initials", () => {
    expect(foldInitial("geist")).toBe("G");
    expect(foldInitial("ß")).toBe("SS");
  });

  it("returns empty string for empty input", () => {
    expect(foldInitial("")).toBe("");
  });
});

describe("alphabetFor", () => {
  it("returns the Greek alphabet for grc and Latin A–Z otherwise", () => {
    expect(alphabetFor("grc")).toBe(GREEK_AZ);
    expect(alphabetFor("grc")[0]).toBe("Α");
    expect(alphabetFor("grc")).toHaveLength(24);
    expect(alphabetFor("deu")).toBe(AZ);
    expect(alphabetFor("lat")).toBe(AZ);
  });
});

describe("language-aware morph labels", () => {
  it("uses classical Acc/Voc + dual for Greek & Latin", () => {
    expect(caseLabelFor("grc").Acc).toBe("Acc");
    expect(caseLabelFor("lat").Voc).toBe("Voc");
    expect(numberLabelFor("grc").Dual).toBe("Du");
  });

  it("uses German Akk/Vok for deu", () => {
    expect(caseLabelFor("deu").Acc).toBe("Akk");
    expect(caseLabelFor("deu").Voc).toBe("Vok");
    expect(numberLabelFor("deu").Dual).toBeUndefined();
  });
});
