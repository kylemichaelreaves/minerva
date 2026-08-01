import { describe, expect, it } from "vitest";
import type { SyntaxSentence, SyntaxToken } from "~/api/syntaxApi";
import { applyCorrections, type Correction } from "~/Syntax/corrections/apply";
import { validateDeprel, validateHead } from "~/Syntax/corrections/validate";

// The client half of the correction machinery. Two jobs:
//
// `applyCorrections` mirrors Python's `materialise` — it replays the log over
// the pristine parse. It is what makes the optimistic queue possible (apply
// locally, post, reconcile) and what makes the JSON patch export meaningful:
// a patch reapplied to the pristine parse must reproduce the edited state.
//
// `validateHead`/`validateDeprel` mirror `syntax/validate.py`, so a bad drop
// is refused on the spot with the reason on screen rather than after a round
// trip. The server keeps its own copy — that is the one a script talks to —
// but a refusal the user has to wait for reads as a bug.
//
// Corrections are chunk-scoped while CoNLL-U ids restart at 1 in every
// sentence, so replay takes the whole document. Nothing else can tell token 1
// of sentence 0 from token 1 of sentence 1.

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

const tok = (id: number, head: number | null, deprel: string): SyntaxToken => ({
  id,
  form: `w${String(id)}`,
  lemma: null,
  upos: null,
  xpos: null,
  feats: null,
  misc: null,
  head,
  deprel,
  start: id,
  end: id + 1,
  corrected: false,
});

/** `1 -> 2 -> 3`, 3 is the root. */
const chain = (): SyntaxToken[] => [tok(1, 2, "det"), tok(2, 3, "nsubj"), tok(3, 0, "root")];

/** One sentence, the chain above. */
const doc = (): SyntaxSentence[] => [{ sent_ord: 0, tokens: chain() }];

const corr = (
  id: number,
  tokId: number,
  kind: "head" | "deprel",
  toVal: string,
  sentOrd = 0,
): Correction => ({ id, sentOrd, tokId, kind, toVal });

describe("applyCorrections", () => {
  it("returns the parse untouched when there are no corrections", () => {
    expect(applyCorrections(doc(), [])).toEqual(doc());
  });

  it("replays a relabelling", () => {
    const out = applyCorrections(doc(), [corr(1, 1, "deprel", "nmod")]);

    expect(at(at(out, 0).tokens, 0).deprel).toBe("nmod");
    expect(at(at(out, 0).tokens, 0).corrected).toBe(true);
  });

  it("replays a reattachment", () => {
    const out = applyCorrections(doc(), [corr(1, 1, "head", "3")]);

    expect(at(at(out, 0).tokens, 0).head).toBe(3);
    expect(at(at(out, 0).tokens, 0).corrected).toBe(true);
  });

  it("leaves tokens no correction names alone", () => {
    const out = applyCorrections(doc(), [corr(1, 1, "deprel", "nmod")]);

    expect(at(at(out, 0).tokens, 1)).toEqual(at(chain(), 1));
    expect(at(at(out, 0).tokens, 2).corrected).toBe(false);
  });

  it("does not mutate the parse it was given", () => {
    const pristine = doc();

    applyCorrections(pristine, [corr(1, 1, "head", "3")]);

    // The pristine parse is the audit trail and the base every replay starts
    // from. Mutating it would make the next replay wrong.
    expect(at(at(pristine, 0).tokens, 0).head).toBe(2);
    expect(at(at(pristine, 0).tokens, 0).corrected).toBe(false);
  });

  it("applies in id order however the log arrives", () => {
    const out = applyCorrections(doc(), [
      corr(2, 1, "deprel", "amod"),
      corr(1, 1, "deprel", "nmod"),
    ]);

    // id order is edit order, so the later edit wins regardless of array order.
    expect(at(at(out, 0).tokens, 0).deprel).toBe("amod");
  });

  it("ignores a correction addressing a token that is not there", () => {
    // The log has no foreign key precisely so it outlives a re-ingest. A patch
    // that no longer lines up has to be inert rather than fatal.
    const out = applyCorrections(doc(), [corr(1, 99, "deprel", "nmod")]);

    expect(out).toEqual(doc());
  });

  it("keeps sentences apart", () => {
    const two: SyntaxSentence[] = [
      { sent_ord: 0, tokens: chain() },
      { sent_ord: 1, tokens: [tok(1, 0, "root")] },
    ];

    const out = applyCorrections(two, [corr(1, 1, "deprel", "nmod", 1)]);

    // Token 1 of sentence 0 must not be touched by an edit to token 1 of
    // sentence 1 — CoNLL-U ids restart in every sentence.
    expect(at(at(out, 0).tokens, 0).deprel).toBe("det");
    expect(at(at(out, 1).tokens, 0).deprel).toBe("nmod");
  });
});

describe("validateHead", () => {
  it("accepts a legal reattachment", () => {
    expect(validateHead(chain(), 1, 3)).toBeNull();
  });

  it("refuses attaching a token to itself", () => {
    expect(validateHead(chain(), 2, 2)?.code).toBe("cycle");
  });

  it("refuses a head inside the token's own subtree", () => {
    const refusal = validateHead(chain(), 2, 1);

    expect(refusal?.code).toBe("cycle");
    expect(refusal?.tokens).toEqual([2, 1]);
  });

  it("names both words in the cycle refusal", () => {
    // Frame 08 renders this verbatim: "w1 is inside the subtree of w2."
    expect(validateHead(chain(), 2, 1)?.message).toContain("w1");
    expect(validateHead(chain(), 2, 1)?.message).toContain("w2");
  });

  it("refuses a head that is not a token in the sentence", () => {
    expect(validateHead(chain(), 1, 9)?.code).toBe("unknown-head");
  });

  it("refuses moving the only root off zero", () => {
    // Also a cycle — the root governs everything — but the root refusal is
    // the one that tells the user what to do about it.
    const refusal = validateHead(chain(), 3, 2);

    expect(refusal?.code).toBe("no-root");
    expect(refusal?.message).toContain("give the root to another token first");
  });

  it("refuses promoting a second token to root", () => {
    const refusal = validateHead(chain(), 1, 0);

    expect(refusal?.code).toBe("two-roots");
    expect(refusal?.tokens).toEqual([1, 3]);
  });

  it("terminates on a tree that already contains a loop", () => {
    const looped = [tok(1, 2, "dep"), tok(2, 1, "dep"), tok(3, 0, "root")];

    // Must return rather than hang. Data we did not produce can be anything.
    expect(() => validateHead(looped, 3, 1)).not.toThrow();
  });
});

describe("validateDeprel", () => {
  it("accepts a plain relation", () => {
    expect(validateDeprel("nsubj")).toBeNull();
  });

  it("accepts a subtyped relation", () => {
    expect(validateDeprel("acl:relcl")).toBeNull();
  });

  it("refuses anything not in the inventory", () => {
    // Stricter than the server, which only checks the shape. The picker is a
    // closed list, so the client can afford to be exact — and a relation the
    // picker cannot produce should never reach the wire.
    for (const bad of ["", "Sb", "nsubj ", "ojb", "ROOT", "a:b:c"]) {
      expect(validateDeprel(bad), bad).not.toBeNull();
    }
  });
});
