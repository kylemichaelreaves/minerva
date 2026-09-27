// @vitest-environment node
/**
 * Retagging a token's part of speech, end to end through the store and out
 * into the layout (#253).
 *
 * The store half mirrors what `syntaxStore.test.ts` already pins for relabel
 * and reattach. The layout half is the part that makes this issue more than a
 * missing field: `upos` is read by the row packer and the field model, so a
 * retag has to move the *drawing*, not just the token's own label. Those
 * assertions are the regression guard — a future refactor that memoises rows
 * on token identity alone would pass every store test and silently freeze the
 * diagram.
 */
import { createRoot } from "solid-js";
import { describe, expect, it, vi } from "vitest";
import type { CorrectionAccepted, SyntaxSentence, SyntaxToken } from "~/api/syntaxApi";
import { applyCorrections, type Correction } from "~/Syntax/corrections/apply";
import { createCorrectionStore, type CorrectionTransport } from "~/Syntax/corrections/store";
import { breakRows } from "~/Syntax/layout/rows";
import { topologicalFields } from "~/Syntax/layout/fields";
import { must } from "./helpers/must";

function at<T>(xs: readonly T[], i: number): T {
  const v = xs[i];
  if (v === undefined) throw new Error(`no element at ${String(i)}`);
  return v;
}

const tok = (
  id: number,
  head: number | null,
  deprel: string,
  upos: string | null = null,
): SyntaxToken => ({
  id,
  form: `w${String(id)}`,
  lemma: null,
  upos,
  xpos: null,
  feats: null,
  misc: null,
  head,
  deprel,
  start: id,
  end: id + 1,
  corrected: false,
});

const doc = (): SyntaxSentence[] => [
  {
    sent_ord: 0,
    tokens: [tok(1, 2, "det", "DET"), tok(2, 3, "nsubj", "NOUN"), tok(3, 0, "root", "VERB")],
  },
];

const accepted = (id: number, token: SyntaxToken): CorrectionAccepted => ({
  id,
  chunk_id: "abc",
  sent_ord: 0,
  token,
  corrections: id,
});

function okTransport(): CorrectionTransport {
  let next = 100;
  return {
    post: vi.fn<CorrectionTransport["post"]>((_chunkId, req) => {
      const base = at(must(doc()[0]).tokens, req.tokId - 1);
      const patched: SyntaxToken = { ...base, corrected: true };
      if (req.kind === "upos") patched.upos = req.toVal;
      if (req.kind === "deprel") patched.deprel = req.toVal;
      if (req.kind === "head") patched.head = Number(req.toVal);
      return Promise.resolve(accepted(next++, patched));
    }),
    remove: vi.fn(() => Promise.resolve()),
  };
}

async function withStore(
  transport: CorrectionTransport,
  body: (store: ReturnType<typeof createCorrectionStore>) => Promise<void> | void,
): Promise<void> {
  let dispose = () => {
    /* replaced below */
  };
  const store = createRoot((d) => {
    dispose = d;
    return createCorrectionStore(
      () => "abc",
      () => doc(),
      transport,
    );
  });
  try {
    await body(store);
  } finally {
    dispose();
  }
}

describe("replay", () => {
  it("applies a upos correction to the named token only", () => {
    const out = applyCorrections(doc(), [
      { id: 1, sentOrd: 0, tokId: 1, kind: "upos", toVal: "PRON", fromVal: "DET" },
    ]);

    expect(at(at(out, 0).tokens, 0).upos).toBe("PRON");
    expect(at(at(out, 0).tokens, 0).corrected).toBe(true);
    expect(at(at(out, 0).tokens, 1).upos).toBe("NOUN");
  });

  it("never mutates the pristine parse", () => {
    const pristine = doc();
    applyCorrections(pristine, [
      { id: 1, sentOrd: 0, tokId: 1, kind: "upos", toVal: "PRON", fromVal: "DET" },
    ]);

    expect(at(at(pristine, 0).tokens, 0).upos).toBe("DET");
  });

  it("keeps a retag and a relabel on one token independent", () => {
    const log: Correction[] = [
      { id: 1, sentOrd: 0, tokId: 1, kind: "upos", toVal: "PRON", fromVal: "DET" },
      { id: 2, sentOrd: 0, tokId: 1, kind: "deprel", toVal: "nsubj", fromVal: "det" },
    ];
    const t = at(at(applyCorrections(doc(), log), 0).tokens, 0);

    expect(t.upos).toBe("PRON");
    expect(t.deprel).toBe("nsubj");
  });

  it("lets the later retag of a token win regardless of arrival order", () => {
    const log: Correction[] = [
      { id: 2, sentOrd: 0, tokId: 1, kind: "upos", toVal: "ADV", fromVal: "PRON" },
      { id: 1, sentOrd: 0, tokId: 1, kind: "upos", toVal: "PRON", fromVal: "DET" },
    ];

    expect(at(at(applyCorrections(doc(), log), 0).tokens, 0).upos).toBe("ADV");
  });
});

describe("store.retag", () => {
  it("shows the new tag and marks the token corrected", async () => {
    await withStore(okTransport(), async (store) => {
      const ok = await store.retag(0, 1, "PRON");

      expect(ok).toBe(true);
      const t = at(at(store.sentences(), 0).tokens, 0);
      expect(t.upos).toBe("PRON");
      expect(t.corrected).toBe(true);
    });
  });

  it("sends kind=upos with the canonical tag and no fromVal", async () => {
    const transport = okTransport();
    await withStore(transport, async (store) => {
      await store.retag(0, 2, "PROPN");

      // `fromVal` is deliberately absent from the wire: the server derives it
      // from the tree the edit actually landed on, so a client-supplied value
      // could disagree with it.
      expect(transport.post).toHaveBeenCalledWith("abc", {
        sentOrd: 0,
        tokId: 2,
        kind: "upos",
        toVal: "PROPN",
      });
    });
  });

  it("keeps the previous tag locally, for the inspector's provenance line", async () => {
    await withStore(okTransport(), async (store) => {
      await store.retag(0, 2, "PROPN");

      const entry = store.corrections().find((c) => c.kind === "upos");
      expect(entry?.fromVal).toBe("NOUN");
    });
  });

  it("refuses a tag outside the inventory without calling the server", async () => {
    const transport = okTransport();
    await withStore(transport, async (store) => {
      const ok = await store.retag(0, 1, "PRELS");

      expect(ok).toBe(false);
      expect(transport.post).not.toHaveBeenCalled();
      expect(store.refusal()?.code).toBe("bad-upos");
      // And the tree is untouched.
      expect(at(at(store.sentences(), 0).tokens, 0).upos).toBe("DET");
    });
  });

  it("counts a retagged token as corrected", async () => {
    await withStore(okTransport(), async (store) => {
      await store.retag(0, 1, "PRON");

      expect(store.correctedTokens(0)).toBe(1);
    });
  });
});

describe("the layout follows the tag", () => {
  // These are the assertions the issue is really about.

  it("re-breaks rows when a token becomes PUNCT", () => {
    // `breakRows` prefers to break just after punctuation, but only inside the
    // last BREAK_ZONE (20%) of the measure. At 40px tokens and an 18px gap a
    // row holds 8, so the zone is tokens 7-8 and only a comma there moves the
    // break — which is why this fixture is 16 tokens and not 6.
    const ids = Array.from({ length: 16 }, (_, i) => i + 1);
    const widths = ids.map(() => 40);
    const plain = ids.map((id) => tok(id, id === 16 ? 0 : id + 1, "dep", "NOUN"));
    const withPunct = plain.map((t) => (t.id === 7 ? { ...t, upos: "PUNCT" } : t));

    const before = breakRows(plain, widths, 450);
    const after = breakRows(withPunct, widths, 450);

    expect(at(before, 0)).toEqual([1, 2, 3, 4, 5, 6, 7, 8]);
    // The break moves to land immediately *after* the punctuation, which
    // shifts every following row — and so every arc's x-coordinate.
    expect(at(after, 0)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(after).not.toEqual(before);
  });

  it("drops LINKE KLAMMER when the finite verb is retagged out of VERB/AUX", () => {
    // `isFiniteVerb` is `VERBAL.has(upos) && feats has VerbForm=Fin`, and it
    // anchors the left bracket — with no finite verb there are no fields at
    // all. Retagging the verb therefore has to change the field model.
    const fin = "VerbForm=Fin";
    const verbal: SyntaxToken[] = [
      tok(1, 2, "nsubj", "NOUN"),
      { ...tok(2, 0, "root", "VERB"), feats: fin },
      tok(3, 2, "obj", "NOUN"),
    ];
    const retagged = verbal.map((t) => (t.id === 2 ? { ...t, upos: "X" } : t));

    const before = topologicalFields(verbal);
    const after = topologicalFields(retagged);

    expect(before.length).toBeGreaterThan(0);
    expect(before.some((f) => f.name === "LK")).toBe(true);
    expect(after).toEqual([]);
  });
});
