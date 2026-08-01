// The topological-field model — Vorfeld, linke Klammer, Mittelfeld, rechte
// Klammer, Nachfeld — derived from the dependency tree rather than annotated.
//
// This is the one layer of the overlay that is *inferred* rather than parsed
// or hand-corrected, which is why it renders in the derived colour, dashed,
// and behind a toggle. It is a heuristic and it will be wrong on complex
// sentences. That is acceptable here in a way it would not be elsewhere: when
// it is wrong the user corrects the tree and the fields recompute, which is a
// real workflow rather than a hypothetical one.
//
// Deliberately not special-cased to raise its accuracy. Every exception added
// here is an exception that has to be right on Hegel, and the honest failure
// (no bracket) is cheaper than a confident wrong one.
//
// The rule below is the *corrected* one. The source brief defines the right
// bracket as "the tokens depending on the LK", which is inverted for UD: UD
// makes the participle the head and the finite auxiliary its `aux` dependent,
// so on `Der Geist hat sich in der Geschichte entwickelt` nothing depends on
// `hat`, the RK computes empty, and the Mittelfeld swallows the clause. See
// *Two corrections to the source brief* in docs/syntax-annotation-plan.md.

/** The minimum a field assignment needs from a token. Both the CoNLL-U
 *  `Token` and the API's `SyntaxToken` satisfy it structurally. */
export interface FieldToken {
  id: number;
  upos?: string | null;
  feats?: string | null;
  head?: number | null;
  deprel?: string | null;
}

export type FieldName = "VF" | "LK" | "MF" | "RK" | "NF";

/** Abbreviation → the full German name, for the band's tooltip. The renderer
 *  keys its labels off this, so the two cannot drift apart. */
export const FIELD_NAMES: Record<FieldName, string> = {
  VF: "Vorfeld",
  LK: "Linke Klammer",
  MF: "Mittelfeld",
  RK: "Rechte Klammer",
  NF: "Nachfeld",
};

export interface Field {
  name: FieldName;
  /** Ids of the tokens assigned to this field, ascending. Never empty — an
   *  empty field is omitted rather than drawn as a zero-width band. */
  tokens: number[];
}

/** UPOS tags a finite verb can carry. */
const VERBAL = new Set(["VERB", "AUX"]);

/** Relations that pull a dependent of the verbal head into the right bracket
 *  with it: the rest of the verbal complex, and the separable prefix. */
const RK_DEPS = new Set(["aux", "aux:pass", "xcomp", "compound:prt"]);

/** Relations by which a finite verb hangs *under* the non-finite head that
 *  carries the lexical content — the shape the corrected rule turns on. */
const AUX_DEPS = new Set(["aux", "aux:pass"]);

const isFiniteVerb = (t: FieldToken): boolean =>
  VERBAL.has(t.upos ?? "") && (t.feats ?? "").split("|").includes("VerbForm=Fin");

/**
 * The finite verb holding the left bracket.
 *
 * Several tokens in a sentence can be finite — every subordinate clause has
 * one — and the field model here describes a single matrix clause, so one has
 * to be chosen. Anchoring at the root picks the matrix clause's verb without
 * any clause segmentation: in UD the root is either the finite verb itself or
 * the non-finite head whose `aux` is finite. Only when the root's own verbal
 * complex has no finite member does this fall back to the first finite verb in
 * the sentence, which is the brief's literal rule.
 */
function findLeftBracket(tokens: readonly FieldToken[]): FieldToken | undefined {
  const root = tokens.find((t) => t.head === 0);
  if (root) {
    if (isFiniteVerb(root)) return root;
    const aux = tokens.find(
      (t) => t.head === root.id && AUX_DEPS.has(t.deprel ?? "") && isFiniteVerb(t),
    );
    if (aux) return aux;
  }
  return tokens.find(isFiniteVerb);
}

/**
 * The right bracket: the token ids closing the verbal frame, ascending.
 *
 * May legitimately be empty — a simple present-tense clause with no particle
 * has no right bracket, and its Mittelfeld runs to the end of the clause.
 */
function findRightBracket(
  tokens: readonly FieldToken[],
  lk: FieldToken,
  byId: ReadonlyMap<number, FieldToken>,
): number[] {
  const rk: number[] = [];

  if (AUX_DEPS.has(lk.deprel ?? "")) {
    // The finite verb is an auxiliary: its head is the non-finite verb that
    // closes the frame, and the rest of the complex hangs off *that*.
    const v = lk.head == null ? undefined : byId.get(lk.head);
    if (v) {
      rk.push(v.id);
      for (const t of tokens) {
        if (t.head === v.id && RK_DEPS.has(t.deprel ?? "")) rk.push(t.id);
      }
    }
  } else {
    // The finite verb holds the frame open by itself; only a particle or a
    // non-finite complement closes it.
    for (const t of tokens) {
      if (t.head === lk.id && (t.deprel === "compound:prt" || t.deprel === "xcomp")) rk.push(t.id);
    }
  }

  // A right bracket left of the left one is the heuristic contradicting
  // itself — verb-final subordination promoted to root, most often. The
  // fields are ordered by definition, so an inverted pair cannot be drawn;
  // reporting no right bracket is the honest degenerate answer.
  return rk.filter((id) => id > lk.id).sort((a, b) => a - b);
}

/**
 * Assign a sentence's tokens to topological fields.
 *
 * Returns the non-empty fields in surface order, or `[]` when no finite verb
 * can be found — a heading, a fragment, an infinitival. Punctuation is never
 * assigned: without that exclusion the full stop lands in the Nachfeld and
 * every sentence reads as extraposed.
 */
export function topologicalFields(tokens: readonly FieldToken[]): Field[] {
  const lk = findLeftBracket(tokens);
  if (!lk) return [];

  const byId = new Map(tokens.map((t) => [t.id, t]));
  const rk = findRightBracket(tokens, lk, byId);
  const rkStart = rk[0] ?? Number.POSITIVE_INFINITY;
  const rkEnd = rk[rk.length - 1] ?? Number.POSITIVE_INFINITY;

  const words = tokens.filter((t) => t.upos !== "PUNCT" && t.id !== lk.id && !rk.includes(t.id));

  const fields: Field[] = [
    { name: "VF", tokens: words.filter((t) => t.id < lk.id).map((t) => t.id) },
    { name: "LK", tokens: [lk.id] },
    { name: "MF", tokens: words.filter((t) => t.id > lk.id && t.id < rkStart).map((t) => t.id) },
    { name: "RK", tokens: rk },
    { name: "NF", tokens: words.filter((t) => t.id > rkEnd).map((t) => t.id) },
  ];

  return fields.filter((f) => f.tokens.length > 0);
}

/**
 * Split a field's tokens into the runs a row can draw as single bands.
 *
 * A band is drawn from the left edge of its first token to the right edge of
 * its last, so a field with a gap in it must not be drawn as one band — the
 * bracket would cover tokens it never claimed. `xcomp` in the right bracket is
 * the case that bites: `hat versucht … das zu tun` claims both verbs and
 * nothing between them.
 *
 * Punctuation is transparent rather than a break. It is excluded from
 * assignment by rule, not because the heuristic failed on it, so a comma
 * inside the Mittelfeld should not saw the Mittelfeld in half.
 *
 * *rowIds* is one row's tokens in surface order; ids of the field that are not
 * on this row are ignored, which is what makes a field spanning a wrap draw
 * one band per row.
 */
export function fieldRuns(
  claimed: readonly number[],
  rowIds: readonly number[],
  isPunct: (id: number) => boolean,
): number[][] {
  const inField = new Set(claimed);
  const runs: number[][] = [];
  let run: number[] = [];
  /** Punctuation seen since the last claimed token, held until one follows. */
  let held: number[] = [];

  for (const id of rowIds) {
    if (inField.has(id)) {
      run.push(...held, id);
      held = [];
    } else if (run.length > 0 && isPunct(id)) {
      held.push(id);
    } else if (run.length > 0) {
      runs.push(run);
      run = [];
      held = [];
    }
  }
  if (run.length > 0) runs.push(run);

  return runs;
}
