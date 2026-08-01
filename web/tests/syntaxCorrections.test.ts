import { describe, expect, it } from "vitest";
import type { SyntaxSentence, SyntaxToken } from "~/api/syntaxApi";
import { applyCorrections, type Correction } from "~/Syntax/corrections/apply";
import { legalHeads, validateDeprel, validateHead } from "~/Syntax/corrections/validate";

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

describe("legalHeads", () => {
  it("offers every token outside the dependent's own subtree", () => {
    // 1 -> 2 -> 3. Token 2 governs 1, so 1 is not available to it; 3 is.
    expect(legalHeads(chain(), 2)).toEqual([3]);
  });

  it("offers the root slot when the token is not already the root", () => {
    // Attaching 1 to ROOT would make two roots, so 0 is not on offer.
    expect(legalHeads(chain(), 1)).toEqual([2, 3]);
  });

  it("offers the root slot to a token in a rootless sentence", () => {
    const rootless = [tok(1, 2, "det"), tok(2, null, "_")];

    expect(legalHeads(rootless, 2)).toContain(0);
  });

  it("never offers the token itself", () => {
    expect(legalHeads(chain(), 3)).not.toContain(3);
  });

  it("offers the only root nowhere to go but where it already is", () => {
    // Every other token is inside its subtree, so the root slot it already
    // occupies is all that is left. The current head stays in the list on
    // purpose: ringing it lets a reattachment be abandoned by putting the
    // token back, and hiding it would make the current attachment look
    // illegal.
    expect(legalHeads(chain(), 3)).toEqual([0]);
  });

  it("excludes a deep descendant, not just a direct child", () => {
    // 1 -> 2 -> 3 -> 4; token 3 governs 2 and 1 transitively.
    const deep = [tok(1, 2, "det"), tok(2, 3, "nmod"), tok(3, 4, "obj"), tok(4, 0, "root")];

    expect(legalHeads(deep, 3)).toEqual([4]);
  });

  it("agrees with validateHead on every token in the sentence", () => {
    // The set and the predicate must not drift: a ring the user can see but
    // not drop on, or a drop that is refused after it looked legal, are both
    // worse than either alone.
    const deep = [tok(1, 2, "det"), tok(2, 3, "nmod"), tok(3, 4, "obj"), tok(4, 0, "root")];

    for (const t of deep) {
      const offered = legalHeads(deep, t.id);
      for (const candidate of [0, 1, 2, 3, 4]) {
        expect(offered.includes(candidate), `${String(t.id)} -> ${String(candidate)}`).toBe(
          validateHead(deep, t.id, candidate) === null,
        );
      }
    }
  });
});
