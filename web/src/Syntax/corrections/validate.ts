import type { SyntaxToken } from "~/api/syntaxApi";
import { isKnownRelation } from "./relations";

// The two refusals, client-side — the mirror of `src/minerva/syntax/validate.py`.
//
// The server keeps its own copy and that is the authoritative one: it is what
// a script talks to, and it is what stops a race between two tabs. This copy
// exists for latency. The design is explicit that both refusals happen *at
// the drop, before the write*, with the reason on screen rather than in a
// toast that leaves — and a refusal you have to wait a round trip for reads
// as a bug rather than as a rule.
//
// Keep the two in step. If a rule changes here it changes in the Python.

export type RefusalCode =
  // Structural — decided here, before anything is sent.
  | "cycle"
  | "no-root"
  | "two-roots"
  | "unknown-head"
  | "unknown-token"
  | "bad-deprel"
  // The server said no. It sees writes from other tabs and from scripts, so
  // it can refuse an edit this copy thought was fine. The reason is whatever
  // it sent back.
  | "conflict"
  // Never got an answer. Distinct from a refusal because nothing was decided:
  // the edit is not wrong, it is unsaved.
  | "network";

export interface Refusal {
  code: RefusalCode;
  /** Shown verbatim in the refusal panel. Names words, not indices. */
  message: string;
  /** The tokens to flash. */
  tokens: number[];
}

/** The heading above the reason, per frame 08's "Refused · cycle". */
export const REFUSAL_TITLE: Record<RefusalCode, string> = {
  cycle: "Refused · cycle",
  "no-root": "Refused · the root",
  "two-roots": "Refused · two roots",
  "unknown-head": "Refused · no such token",
  "unknown-token": "Refused · no such token",
  "bad-deprel": "Refused · unknown relation",
  conflict: "Refused",
  network: "Not saved",
};

/**
 * Whether *tokId* may be reattached to *newHead* within one sentence.
 * `null` means yes.
 *
 * `tokens` must be a single sentence's tokens: CoNLL-U ids restart at 1 in
 * every sentence, so a list spanning two would confuse two different words.
 */
export function validateHead(
  tokens: readonly SyntaxToken[],
  tokId: number,
  newHead: number,
): Refusal | null {
  const byId = new Map(tokens.map((t) => [t.id, t]));

  const token = byId.get(tokId);
  if (token === undefined) {
    return { code: "unknown-token", message: `There is no token ${String(tokId)}.`, tokens: [tokId] };
  }

  if (newHead === tokId) {
    return { code: "cycle", message: `${token.form} cannot be its own head.`, tokens: [tokId] };
  }

  if (newHead !== 0 && !byId.has(newHead)) {
    return {
      code: "unknown-head",
      message: `There is no token ${String(newHead)} in this sentence.`,
      tokens: [tokId, newHead],
    };
  }

  // ---- root, before cycles ----
  //
  // Order matters. In a well-formed tree the root governs every token, so
  // *every* reattachment of the root is also a cycle. Saying so would be true
  // and useless; "give the root to another token first" is the sentence that
  // tells the user what to do.
  const otherRoots = tokens.filter((t) => t.head === 0 && t.id !== tokId).map((t) => t.id);
  const [incumbentId] = otherRoots;

  if (newHead === 0 && incumbentId !== undefined) {
    const incumbent = byId.get(incumbentId);
    return {
      code: "two-roots",
      message: `${incumbent?.form ?? "Another token"} is already the root of this sentence. A sentence has exactly one.`,
      tokens: [tokId, ...otherRoots],
    };
  }

  if (newHead !== 0 && token.head === 0 && otherRoots.length === 0) {
    return {
      code: "no-root",
      message: `${token.form} is the sentence root — give the root to another token first.`,
      tokens: [tokId],
    };
  }

  // ---- cycles ----
  //
  // Walk up from the proposed head; reaching tokId means the head lies inside
  // its own dependent's subtree. `seen` guards a loop that already exists in
  // the data and does not pass through tokId — the walk must terminate over a
  // tree we did not produce.
  const path = [tokId];
  const seen = new Set([tokId]);
  let cursor: number | null = newHead;
  while (cursor !== 0 && cursor !== null) {
    if (cursor === tokId) {
      return {
        code: "cycle",
        message:
          `${byId.get(newHead)?.form ?? "That token"} is inside the subtree of ${token.form}. ` +
          "A head must lie outside its dependent's subtree, or the sentence stops being a tree.",
        tokens: path,
      };
    }
    if (seen.has(cursor)) break;
    seen.add(cursor);
    path.push(cursor);
    const next: SyntaxToken | undefined = byId.get(cursor);
    if (next === undefined) break;
    cursor = next.head;
  }

  return null;
}

/**
 * Whether *deprel* is a relation the picker could have produced. `null` means
 * yes.
 *
 * Stricter than the server, which checks only the shape. Here the closed
 * inventory is right there, so a relation the picker cannot offer should
 * never reach the wire.
 */
export function validateDeprel(deprel: string): Refusal | null {
  if (!isKnownRelation(deprel)) {
    return {
      code: "bad-deprel",
      message: `"${deprel}" is not a Universal Dependencies relation.`,
      tokens: [],
    };
  }
  return null;
}

/**
 * Every head *tokId* may legally be attached to, in token order, with `0`
 * (the sentence root) first when it is on offer.
 *
 * Derived by asking `validateHead` about each candidate rather than by
 * reimplementing the rules. The set and the predicate must not drift: a
 * candidate the user can see but not drop on, and a drop refused after it
 * looked legal, are both worse than either failure alone.
 *
 * Drives the candidate rings, the keyboard target cycle, and drop-target
 * validity — one answer for all three.
 */
export function legalHeads(tokens: readonly SyntaxToken[], tokId: number): number[] {
  const candidates = [0, ...tokens.map((t) => t.id)];
  return candidates.filter((head) => validateHead(tokens, tokId, head) === null);
}
