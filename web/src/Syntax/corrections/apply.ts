import type { CorrectionRow, SyntaxSentence, SyntaxToken } from "~/api/syntaxApi";

// Replaying the correction log over the pristine parse — the TypeScript
// mirror of `materialise` in `src/minerva/syntax/queries.py`.
//
// Two callers depend on it being pure and total:
//
//  * the optimistic store, which applies an edit locally, posts it, and
//    reconciles — so the same input must always give the same tree;
//  * the JSON patch export, whose acceptance criterion is that a patch
//    reapplied to the pristine parse reproduces the edited state. That is
//    only meaningful if replay here matches replay on the server.

/** One entry in the append-only log. `id` is also its replay position. */
export interface Correction {
  id: number;
  sentOrd: number;
  tokId: number;
  kind: "head" | "deprel" | "upos";
  /** Always a string on the wire; `head` round-trips through `Number`. */
  toVal: string;
  /** The value at the time of the edit. Provenance — the inspector's "was obj". */
  fromVal?: string | null;
}

/** The API's snake_case log row as the camelCase shape replay works on. */
export function fromApi(row: CorrectionRow): Correction {
  return {
    id: row.id,
    sentOrd: row.sent_ord,
    tokId: row.tok_id,
    kind: row.kind,
    toVal: row.to_val,
    fromVal: row.from_val,
  };
}

const key = (sentOrd: number, tokId: number): string => `${String(sentOrd)}:${String(tokId)}`;

/**
 * The tree as it currently stands: *sentences* with *corrections* replayed
 * over them.
 *
 * Corrections are applied in `id` order regardless of the order they arrive
 * in — the log is append-only, so id order is edit order and a later edit to
 * the same token supersedes an earlier one. A correction addressing a token
 * that is not present is ignored rather than throwing: the log has no foreign
 * key precisely so it survives a re-ingest, and a patch that no longer lines
 * up must be inert, not fatal.
 *
 * Never mutates its input. The pristine parse is the audit trail and the base
 * every subsequent replay starts from.
 */
export function applyCorrections(
  sentences: readonly SyntaxSentence[],
  corrections: readonly Correction[],
): SyntaxSentence[] {
  if (corrections.length === 0) return sentences.map((s) => ({ ...s, tokens: [...s.tokens] }));

  // Collapse the log before touching the tree: last write wins, per token and
  // per kind. Keyed by kind as well as token because reattaching a word and
  // relabelling it are independent edits — one must not shadow the other.
  const latest = new Map<string, Correction>();
  for (const c of [...corrections].sort((a, b) => a.id - b.id)) {
    latest.set(`${key(c.sentOrd, c.tokId)}:${c.kind}`, c);
  }

  return sentences.map((sentence) => ({
    ...sentence,
    tokens: sentence.tokens.map((token) => {
      const head = latest.get(`${key(sentence.sent_ord, token.id)}:head`);
      const deprel = latest.get(`${key(sentence.sent_ord, token.id)}:deprel`);
      const upos = latest.get(`${key(sentence.sent_ord, token.id)}:upos`);
      if (head === undefined && deprel === undefined && upos === undefined) return token;
      const next: SyntaxToken = { ...token, corrected: true };
      if (head !== undefined) next.head = Number(head.toVal);
      if (deprel !== undefined) next.deprel = deprel.toVal;
      // A retag returns a NEW token object, which is what makes the row packer
      // and the field model recompute — `upos` feeds both (#253).
      if (upos !== undefined) next.upos = upos.toVal;
      return next;
    }),
  }));
}

/** The correction log as a portable patch, for the JSON export. */
export interface CorrectionPatch {
  chunkId: string;
  /** ISO-8601, stamped at export time. */
  exportedAt: string;
  corrections: Correction[];
}
