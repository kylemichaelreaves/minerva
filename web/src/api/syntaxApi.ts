import { apiDelete, apiGet, apiPost } from "~/api/client";

/** One syntactic word, as `GET /api/chunks/{id}/syntax` returns it. */
export interface SyntaxToken {
  /** 1-based within its sentence, as in CoNLL-U. */
  id: number;
  form: string;
  lemma: string | null;
  upos: string | null;
  /**
   * Language-specific tag. The German tagset says things UPOS cannot — `PRF`
   * for a reflexive, which is the distinction an `expl:pv` correction turns
   * on — and dropping it would make CoNLL-U export lossy.
   */
  xpos: string | null;
  /** Raw UD feature string, `Case=Nom|Gender=Masc|Number=Sing`. */
  feats: string | null;
  /** The CoNLL-U MISC column, carried so export round-trips. */
  misc: string | null;
  /** 0 attaches to the sentence root; null is CoNLL-U's `_`, unparsed. */
  head: number | null;
  deprel: string | null;
  /** Character offsets into the chunk's text. */
  start: number;
  end: number;
  /** True once a hand correction has touched this token. Drives the colour. */
  corrected: boolean;
}

export interface SyntaxSentence {
  sent_ord: number;
  tokens: SyntaxToken[];
}

/** One row of the append-only correction log, as the API returns it. */
export interface CorrectionRow {
  id: number;
  sent_ord: number;
  tok_id: number;
  kind: "head" | "deprel";
  from_val: string | null;
  to_val: string;
}

export interface ChunkSyntax {
  chunk_id: string;
  /**
   * The **pristine** machine parse — corrections are *not* merged in.
   *
   * The client replays `corrections` over this itself. That is what lets undo
   * recompute the tree without one entry, and what lets an edit show
   * instantly instead of after a round trip.
   */
  sentences: SyntaxSentence[];
  /** The correction log for this chunk, in id order. */
  corrections: CorrectionRow[];
}

/**
 * Fetch the dependency trees for one chunk.
 *
 * The first call for a chunk parses it server-side (~4s cold, once per server
 * process, then ~0.15s per paragraph); every later call is a cache read.
 */
export function fetchChunkSyntax(chunkId: string, signal?: AbortSignal): Promise<ChunkSyntax> {
  return apiGet<ChunkSyntax>(`/api/chunks/${encodeURIComponent(chunkId)}/syntax`, signal);
}

/** What the server says after accepting one correction. */
export interface CorrectionAccepted {
  /** The row's id — also its replay position, and what undo addresses. */
  id: number;
  chunk_id: string;
  sent_ord: number;
  /** The token as it now stands, corrections replayed. */
  token: SyntaxToken;
  /** How many corrections this chunk now carries. */
  corrections: number;
}

export interface CorrectionRequest {
  sentOrd: number;
  tokId: number;
  kind: "head" | "deprel";
  /** A head is sent as its decimal string; the column is TEXT for both kinds. */
  toVal: string;
}

/**
 * Append one correction.
 *
 * `fromVal` is deliberately not sent. The server reads the previous value off
 * the tree it is about to change, so provenance cannot disagree with what the
 * correction was actually applied to.
 *
 * Rejects with an `ApiError`: 409 when the edit would break the tree (cycle,
 * or the sentence left with no root or two), 400 when the payload is
 * malformed, 404 when the chunk or token is not there.
 */
export function postCorrection(
  chunkId: string,
  req: CorrectionRequest,
  signal?: AbortSignal,
): Promise<CorrectionAccepted> {
  return apiPost<CorrectionAccepted>(
    `/api/chunks/${encodeURIComponent(chunkId)}/syntax/corrections`,
    { sent_ord: req.sentOrd, tok_id: req.tokId, kind: req.kind, to_val: req.toVal },
    signal,
  );
}

/** Undo one correction. Rejects with a 404 `ApiError` if it is already gone. */
export function deleteCorrection(correctionId: number, signal?: AbortSignal): Promise<void> {
  return apiDelete(`/api/syntax/corrections/${String(correctionId)}`, signal);
}
