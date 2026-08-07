/**
 * The part-of-speech inventory and its validator (#253).
 *
 * Mirrors `src/minerva/syntax/validate.py::UPOS_TAGS` — the server copy is
 * the one that matters, this one is so the picker can refuse without a round
 * trip. If the two ever disagree, the client accepts an edit the server then
 * rejects, which is the failure mode `validateDeprel` already guards against.
 */
import { describe, it, expect } from "vitest";
import {
  POS_TAGS,
  POS_GROUPS,
  filterPos,
  isKnownPos,
  posGloss,
} from "~/Syntax/corrections/pos";
import { validateUpos } from "~/Syntax/corrections/validate";

/** UD v2's closed inventory, spelled out so a drift shows as a diff. */
const UD_17 = [
  "ADJ", "ADP", "ADV", "AUX", "CCONJ", "DET", "INTJ", "NOUN", "NUM",
  "PART", "PRON", "PROPN", "PUNCT", "SCONJ", "SYM", "VERB", "X",
];

describe("the inventory", () => {
  it("is exactly UD's 17 tags", () => {
    expect([...POS_TAGS].map((t) => t.name).sort()).toEqual([...UD_17].sort());
  });

  it("groups every tag exactly once", () => {
    const grouped = POS_GROUPS.flatMap((g) => g.tags.map((t) => t.name));
    expect(grouped.sort()).toEqual([...UD_17].sort());
    expect(new Set(grouped).size).toBe(grouped.length);
  });

  it("glosses every tag", () => {
    for (const tag of UD_17) {
      expect(posGloss(tag), tag).toBeTruthy();
    }
  });

  it("includes PUNCT, which the reader's POS_LABEL map omits", () => {
    // PUNCT is the layout-critical tag: rows break after it and the field
    // bands split around it. Reusing `~/Reader/wordInfoMorph`'s 14-entry
    // display map would have silently made it unpickable.
    expect(isKnownPos("PUNCT")).toBe(true);
    expect(isKnownPos("SYM")).toBe(true);
    expect(isKnownPos("X")).toBe(true);
  });

  it("rejects TIGER/STTS tags, which are shaped like UD tags", () => {
    for (const tiger of ["NN", "NE", "ADJA", "PRELS", "VVFIN", "ART", "APPR"]) {
      expect(isKnownPos(tiger), tiger).toBe(false);
    }
  });
});

describe("filterPos", () => {
  it("returns every group when the query is empty", () => {
    expect(filterPos("")).toEqual(POS_GROUPS);
  });

  it("matches on the tag name, case-insensitively", () => {
    const names = filterPos("propn").flatMap((g) => g.tags.map((t) => t.name));
    expect(names).toEqual(["PROPN"]);
  });

  it("matches on the gloss, so a corrector can type what they mean", () => {
    const names = filterPos("proper").flatMap((g) => g.tags.map((t) => t.name));
    expect(names).toContain("PROPN");
  });

  it("drops groups that filter down to nothing", () => {
    for (const group of filterPos("verb")) {
      expect(group.tags.length).toBeGreaterThan(0);
    }
  });

  it("returns nothing for a TIGER tag, so there is nothing to commit", () => {
    expect(filterPos("PRELS").flatMap((g) => g.tags)).toEqual([]);
  });
});

describe("validateUpos", () => {
  it("accepts every UD tag", () => {
    for (const tag of UD_17) {
      expect(validateUpos(tag), tag).toBeNull();
    }
  });

  it("refuses a TIGER tag by name", () => {
    const refusal = validateUpos("NN");
    expect(refusal?.code).toBe("bad-upos");
    expect(refusal?.message).toContain("NN");
  });

  it("refuses a lower-case tag rather than coercing it", () => {
    // Coercing would put a value in the log the curator was never shown.
    expect(validateUpos("noun")).not.toBeNull();
  });

  it("refuses an empty tag", () => {
    expect(validateUpos("")).not.toBeNull();
  });
});
