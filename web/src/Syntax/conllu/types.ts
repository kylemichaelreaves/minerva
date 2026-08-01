// The CoNLL-U data model, kept deliberately close to the file format: ten
// columns, one row per syntactic word, sentences carrying `#` metadata.
//
// Fidelity to the format matters more here than ergonomics. This is the shape
// hand corrections are exported through, and a lossy model means a lossy
// export — so columns we never read (`xpos`, `deps`, `misc`) are still
// carried, and `head` distinguishes "attached to root" from "not parsed".

/** One syntactic word. Integer `id`, 1-based, as in the format. */
export interface Token {
  id: number;
  form: string;
  lemma: string;
  upos: string;
  xpos: string;
  feats: string;
  /**
   * `0` means the token attaches to the sentence root. `null` is the format's
   * `_` — genuinely unparsed. Collapsing the two would invent a second root
   * for every unannotated token and break the single-root invariant the
   * editor enforces.
   */
  head: number | null;
  deprel: string;
  deps: string;
  misc: string;
}

/**
 * A row that is part of the format but has no place in an arc diagram:
 * a multiword range (`3-4 zum`) spans two syntactic words with no head of its
 * own, and an empty node (`5.1`) has no surface form. Neither carries a usable
 * (id, head) pair, so both are excluded from `Sentence.tokens` — but they are
 * retained verbatim so a round-trip does not silently drop them.
 */
export interface SkippedLine {
  kind: "multiword" | "empty";
  /** The raw first column: `"3-4"`, `"5.1"`. */
  id: string;
  /** Position among the sentence's non-comment lines, 0-based. */
  lineIndex: number;
  /** The untouched source line, re-emitted as-is. */
  raw: string;
}

export interface Sentence {
  /** From `# sent_id = …`, falling back to the sentence's ordinal. */
  sentId: string;
  /** From `# text = …`, when present. */
  text?: string;
  /** Every `#` line, verbatim and in order. */
  comments: string[];
  tokens: Token[];
  skipped: SkippedLine[];
}

export interface Document {
  sentences: Sentence[];
}
