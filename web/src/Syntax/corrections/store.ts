import { createMemo, createSignal } from "solid-js";
import { ApiError } from "~/api/client";
import {
  deleteCorrection,
  postCorrection,
  type CorrectionAccepted,
  type CorrectionRequest,
  type SyntaxSentence,
} from "~/api/syntaxApi";
import { applyCorrections, type Correction } from "./apply";
import { validateDeprel, validateHead, type Refusal } from "./validate";

// The optimistic correction queue.
//
// Correcting a tree is hand labour done at speed — relabel, look, relabel —
// so the diagram moves the instant the user commits and reconciles behind
// them. Everything interesting here is therefore about going backwards: a
// refused edit, a dropped connection, an undo the server rejects. An edit
// that is visible but not saved is worse than a slow one, so a rollback has
// to leave no trace at all.
//
// Two layers of refusal, on purpose:
//
//  1. `validate*` runs first, locally. Illegal edits never reach the wire,
//     and the reason is on screen in the same frame as the drop.
//  2. The server checks again and can still say no — it sees writes from
//     other tabs and from scripts. That refusal rolls back the same way.

/** The network calls the store makes. Injected so tests can drive them. */
export interface CorrectionTransport {
  post: (chunkId: string, req: CorrectionRequest) => Promise<CorrectionAccepted>;
  remove: (correctionId: number) => Promise<void>;
}

export const httpTransport: CorrectionTransport = {
  post: (chunkId, req) => postCorrection(chunkId, req),
  remove: (correctionId) => deleteCorrection(correctionId),
};

/**
 * Optimistic ids count down from below zero so they cannot collide with a
 * server id, and so `sort((a, b) => a.id - b.id)` still puts an in-flight
 * edit last — it is, by definition, the most recent one.
 */
let nextOptimisticId = -1;

/**
 * Whether a failure was the server saying no, or the server not answering.
 *
 * The distinction is the whole message. A 4xx is a judgement about the edit
 * and the server's own wording is better than anything reconstructed here —
 * it names the words and says what to do instead. A 5xx or a dropped socket
 * is not a judgement at all; calling it "Refused · 502 Bad Gateway" tells the
 * user their correction was rejected on the merits, which is a lie.
 */
function classify(err: unknown): { code: "conflict" | "network"; message: string } {
  if (err instanceof ApiError && err.status < 500) {
    return { code: "conflict", message: err.message };
  }
  return {
    code: "network",
    message: "Could not reach the server — the correction was not saved.",
  };
}

export function createCorrectionStore(
  chunkId: string,
  pristine: () => readonly SyntaxSentence[],
  transport: CorrectionTransport = httpTransport,
  /**
   * The log already on the server, from the same GET as *pristine*. Seeded
   * into the store so a correction made in an earlier session can still be
   * undone and can still say what it replaced — without it, Revert after a
   * reload is a button that points at nothing.
   */
  saved: () => readonly Correction[] = () => [],
) {
  const [session, setSession] = createSignal<Correction[]>([]);
  const [dropped, setDropped] = createSignal<number[]>([]);
  const [refusal, setRefusal] = createSignal<Refusal | null>(null);
  const [pending, setPending] = createSignal(0);

  /**
   * The whole log: what the server had, less what has been undone, plus what
   * this session has added. Undone ids are tracked rather than removed from
   * `saved` because `saved` is derived from the fetch and would otherwise
   * resurrect them on the next read.
   */
  const corrections = createMemo(() => {
    const gone = new Set(dropped());
    return [...saved().filter((c) => !gone.has(c.id)), ...session()].sort((a, b) => a.id - b.id);
  });

  const setCorrections = (fn: (cur: Correction[]) => Correction[]): void => {
    // Only the session half is directly mutable; dropping a saved row is
    // recorded in `dropped`.
    const before = corrections();
    const after = fn(before);
    const afterIds = new Set(after.map((c) => c.id));
    const savedIds = new Set(saved().map((c) => c.id));
    setDropped(saved().filter((c) => !afterIds.has(c.id)).map((c) => c.id));
    setSession(after.filter((c) => !savedIds.has(c.id)));
  };

  /** The tree as the user sees it: the parse with the log replayed over it. */
  const sentences = createMemo(() => applyCorrections(pristine(), corrections()));

  const tokensOf = (sentOrd: number) =>
    sentences().find((s) => s.sent_ord === sentOrd)?.tokens ?? [];

  function refuse(r: Refusal): void {
    setRefusal(r);
  }

  /** Add an entry locally, post it, and reconcile — or roll it all back. */
  async function commit(entry: Omit<Correction, "id">): Promise<boolean> {
    const optimisticId = nextOptimisticId--;
    const optimistic: Correction = { ...entry, id: optimisticId };

    setRefusal(null);
    setCorrections((cur) => [...cur, optimistic]);
    setPending((n) => n + 1);

    try {
      const saved = await transport.post(chunkId, {
        sentOrd: entry.sentOrd,
        tokId: entry.tokId,
        kind: entry.kind,
        toVal: entry.toVal,
      });
      // Swap the temporary id for the real one in place, so replay order is
      // unchanged and undo has a row it can actually delete.
      setCorrections((cur) =>
        cur.map((c) => (c.id === optimisticId ? { ...c, id: saved.id } : c)),
      );
      return true;
    } catch (err: unknown) {
      setCorrections((cur) => cur.filter((c) => c.id !== optimisticId));
      refuse({ ...classify(err), tokens: [entry.tokId] });
      return false;
    } finally {
      setPending((n) => n - 1);
    }
  }

  return {
    /** The materialised tree. */
    sentences,
    /** The log, in replay order. */
    corrections,
    /** The current refusal, or null. Cleared by the next accepted edit. */
    refusal,
    clearRefusal: () => {
      setRefusal(null);
    },
    /** How many edits are in flight — drives the saving indicator. */
    pending,

    /** How many tokens in a sentence carry a hand correction. */
    correctedTokens: (sentOrd: number) => tokensOf(sentOrd).filter((t) => t.corrected).length,

    /** Relabel one token. Returns whether the edit stuck. */
    async relabel(sentOrd: number, tokId: number, deprel: string): Promise<boolean> {
      const bad = validateDeprel(deprel);
      if (bad !== null) {
        refuse({ ...bad, tokens: [tokId] });
        return false;
      }
      const before = tokensOf(sentOrd).find((t) => t.id === tokId);
      return commit({
        sentOrd,
        tokId,
        kind: "deprel",
        toVal: deprel,
        fromVal: before?.deprel ?? null,
      });
    },

    /** Reattach one token to a new head. `0` makes it the sentence root. */
    async reattach(sentOrd: number, tokId: number, newHead: number): Promise<boolean> {
      // Against the *current* tree, not the machine parse: an edit has to be
      // judged against the one before it, or a correction that legalised this
      // move a moment ago would be ignored.
      const bad = validateHead(tokensOf(sentOrd), tokId, newHead);
      if (bad !== null) {
        refuse(bad);
        return false;
      }
      const before = tokensOf(sentOrd).find((t) => t.id === tokId);
      return commit({
        sentOrd,
        tokId,
        kind: "head",
        toVal: String(newHead),
        fromVal: before?.head == null ? null : String(before.head),
      });
    },

    /** Drop one correction. Restores it if the server refuses. */
    async undo(correctionId: number): Promise<boolean> {
      const removed = corrections().find((c) => c.id === correctionId);
      if (removed === undefined) return false;

      setRefusal(null);
      setCorrections((cur) => cur.filter((c) => c.id !== correctionId));

      try {
        await transport.remove(correctionId);
        return true;
      } catch (err: unknown) {
        // A 404 means the row is already gone, which is what undo wanted.
        // Restoring it would resurrect something that does not exist.
        if (err instanceof ApiError && err.status === 404) return true;
        setCorrections((cur) => [...cur, removed].sort((a, b) => a.id - b.id));
        refuse({
          code: classify(err).code,
          message: "Could not undo that correction — it is still saved.",
          tokens: [removed.tokId],
        });
        return false;
      }
    },
  };
}
