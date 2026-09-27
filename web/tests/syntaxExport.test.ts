// @vitest-environment node
import { describe, expect, it } from "vitest";
import type { SyntaxSentence, SyntaxToken } from "~/api/syntaxApi";
import { parseConllu } from "~/Syntax/conllu/parse";
import { writeConllu } from "~/Syntax/conllu/serialise";
import { applyCorrections, type Correction } from "~/Syntax/corrections/apply";
import { exportConllu, exportPatch, toConlluDocument } from "~/Syntax/corrections/export";

// The two exports, and the property each has to hold.
//
// CoNLL-U is how a corrected tree leaves this tool for anything else — a
// treebank, a parser evaluation, a colleague. It has to reparse; an export
// that only this app can read is not an export.
//
// The JSON patch is how a correction survives the parse being redone. Its
// acceptance criterion is exact: reapplied to the pristine parse, it must
// reproduce the edited state. That is what makes the machine parse safe to
// throw away and recompute.

/**
 * Indexed access that fails loudly. `noUncheckedIndexedAccess` is on, so a
 * bare `xs[0]` is `T | undefined` and every assertion would need a `?.` that
 * quietly passes when the element is missing — which is exactly the bug these
 * tests exist to catch.
 */
function at<T>(xs: readonly T[], i: number): T {
  const v = xs[i];
  if (v === undefined) throw new Error(`no element at ${String(i)}`);
  return v;
}

const tok = (
  id: number,
  form: string,
  head: number | null,
  deprel: string,
  extra: Partial<SyntaxToken> = {},
): SyntaxToken => ({
  id,
  form,
  lemma: form.toLowerCase(),
  upos: "NOUN",
  xpos: null,
  feats: null,
  misc: null,
  head,
  deprel,
  start: id,
  end: id + form.length,
  corrected: false,
  ...extra,
});

const doc = (): SyntaxSentence[] => [
  {
    sent_ord: 0,
    tokens: [
      tok(1, "Der", 2, "det", { upos: "DET", xpos: "ART", feats: "Case=Nom|Gender=Masc" }),
      tok(2, "Geist", 3, "nsubj"),
      tok(3, "entwickelt", 0, "root", { upos: "VERB" }),
    ],
  },
];

describe("toConlluDocument", () => {
  it("carries every column the API returns", () => {
    const first = at(at(toConlluDocument("abc", doc()).sentences, 0).tokens, 0);

    expect(first).toMatchObject({
      id: 1,
      form: "Der",
      lemma: "der",
      upos: "DET",
      xpos: "ART",
      feats: "Case=Nom|Gender=Masc",
      head: 2,
      deprel: "det",
    });
  });

  it("writes an absent column as the format's underscore", () => {
    const second = at(at(toConlluDocument("abc", doc()).sentences, 0).tokens, 1);

    expect(second.xpos).toBe("_");
    expect(second.feats).toBe("_");
    expect(second.misc).toBe("_");
  });

  it("keeps head 0 distinct from an unparsed head", () => {
    const withNull: SyntaxSentence[] = [
      { sent_ord: 0, tokens: [tok(1, "Der", null, "dep"), tok(2, "Geist", 0, "root")] },
    ];

    const tokens = at(toConlluDocument("abc", withNull).sentences, 0).tokens;

    // `null` is the format's `_`; collapsing it to 0 would invent a second root.
    expect(at(tokens, 0).head).toBeNull();
    expect(at(tokens, 1).head).toBe(0);
  });

  it("identifies each sentence by chunk and ordinal", () => {
    const two: SyntaxSentence[] = [...doc(), { sent_ord: 1, tokens: [tok(1, "Ja", 0, "root")] }];

    const ids = toConlluDocument("abc", two).sentences.map((s) => s.sentId);

    expect(ids).toEqual(["abc-0", "abc-1"]);
  });

  it("records the chunk and sentence in the comments", () => {
    const comments = at(toConlluDocument("abc", doc()).sentences, 0).comments;

    expect(comments).toContain("# sent_id = abc-0");
    expect(comments.some((c) => c.startsWith("# text = "))).toBe(true);
  });
});

describe("exportConllu", () => {
  it("reparses cleanly", () => {
    // The acceptance criterion, stated exactly: exported CoNLL-U reparses.
    const text = exportConllu("abc", doc());

    const reparsed = parseConllu(text);

    expect(reparsed.sentences).toHaveLength(1);
    expect(at(reparsed.sentences, 0).tokens.map((t) => t.form)).toEqual([
      "Der",
      "Geist",
      "entwickelt",
    ]);
  });

  it("survives a second round trip byte-identically", () => {
    const text = exportConllu("abc", doc());

    expect(writeConllu(parseConllu(text))).toBe(text);
  });

  it("preserves heads and relations through the round trip", () => {
    const reparsed = parseConllu(exportConllu("abc", doc()));

    expect(at(reparsed.sentences, 0).tokens.map((t) => [t.head, t.deprel])).toEqual([
      [2, "det"],
      [3, "nsubj"],
      [0, "root"],
    ]);
  });

  it("exports the corrected tree, not the machine parse", () => {
    const corrections: Correction[] = [
      { id: 1, sentOrd: 0, tokId: 1, kind: "deprel", toVal: "nmod" },
    ];

    const text = exportConllu("abc", applyCorrections(doc(), corrections));

    expect(at(at(parseConllu(text).sentences, 0).tokens, 0).deprel).toBe("nmod");
  });
});

describe("exportPatch", () => {
  const corrections: Correction[] = [
    { id: 1, sentOrd: 0, tokId: 1, kind: "deprel", toVal: "nmod", fromVal: "det" },
    { id: 2, sentOrd: 0, tokId: 2, kind: "head", toVal: "1", fromVal: "3" },
  ];

  it("reproduces the edited state when reapplied to the pristine parse", () => {
    const edited = applyCorrections(doc(), corrections);

    const patch = exportPatch("abc", corrections);
    const replayed = applyCorrections(doc(), patch.corrections);

    expect(replayed).toEqual(edited);
  });

  it("survives a trip through JSON", () => {
    const patch = exportPatch("abc", corrections);

    const roundTripped = JSON.parse(JSON.stringify(patch)) as typeof patch;

    expect(applyCorrections(doc(), roundTripped.corrections)).toEqual(
      applyCorrections(doc(), corrections),
    );
  });

  it("keeps the provenance a reviewer needs", () => {
    const patch = exportPatch("abc", corrections);

    // `fromVal` is what makes a patch auditable — "was det" is the claim a
    // reviewer checks against the parse it was made from.
    expect(at(patch.corrections, 0).fromVal).toBe("det");
    expect(patch.chunkId).toBe("abc");
    expect(patch.exportedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it("orders the log by id so replay order is stable", () => {
    const patch = exportPatch("abc", [at(corrections, 1), at(corrections, 0)]);

    expect(patch.corrections.map((c) => c.id)).toEqual([1, 2]);
  });
});
