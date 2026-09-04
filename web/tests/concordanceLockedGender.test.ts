import { describe, expect, it } from "vitest";

import { formatGenderShare, lockedGender } from "~/Concordance/constants";

/** #507: the "one gender accounts for >95% of attested forms" heuristic
 *  lived in both `FilterRail` and `LemmaIdentityCard`, and the two copies
 *  did not agree. The card read `props.data.gender_breakdown[0]` — the
 *  API returns those count-descending, so that is the true maximum —
 *  while the rail read `sortBucketsByOrder(..., GENDERS_ORDER)[0]`, the
 *  first of Masc/Fem/Neut *present*. Both receive the same object, so
 *  they contradicted each other on one screen for roughly half the
 *  lemmas the card locked: `ratio` is Fem 17,619 / Masc 50, and the rail
 *  scored Masc's 0.3% against the threshold. */
describe("lockedGender", () => {
  it("returns null with no buckets", () => {
    expect(lockedGender([])).toBeNull();
  });

  it("locks a single-gender lemma at a full share", () => {
    expect(lockedGender([{ value: "Fem", count: 12 }])).toEqual({ value: "Fem", share: 1 });
  });

  it("takes the maximum by count, not the first bucket", () => {
    // The real `ratio` (lat) breakdown, in canonical order — which is
    // the order the rail used to look at.
    expect(
      lockedGender([
        { value: "Masc", count: 50 },
        { value: "Fem", count: 17619 },
      ]),
    ).toEqual({ value: "Fem", share: 17619 / 17669 });
  });

  it("stays null when no gender dominates", () => {
    expect(
      lockedGender([
        { value: "Masc", count: 60 },
        { value: "Fem", count: 40 },
      ]),
    ).toBeNull();
  });

  it("requires strictly more than the threshold", () => {
    expect(
      lockedGender([
        { value: "Masc", count: 95 },
        { value: "Fem", count: 5 },
      ]),
    ).toBeNull();
  });
});

describe("formatGenderShare", () => {
  it("drops the decimal at a whole 100%", () => {
    expect(formatGenderShare(1)).toBe("100%");
  });

  it("keeps one decimal below that", () => {
    expect(formatGenderShare(17619 / 17669)).toBe("99.7%");
    expect(formatGenderShare(0.96)).toBe("96.0%");
  });
});
