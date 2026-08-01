import { apiGet } from "~/api/client";

/** One syntactic word, as `GET /api/chunks/{id}/syntax` returns it. */
export interface SyntaxToken {
  /** 1-based within its sentence, as in CoNLL-U. */
  id: number;
  form: string;
  lemma: string | null;
  upos: string | null;
  /** Raw UD feature string, `Case=Nom|Gender=Masc|Number=Sing`. */
  feats: string | null;
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

export interface ChunkSyntax {
  chunk_id: string;
  sentences: SyntaxSentence[];
  /** How many corrections were replayed over the machine parse. */
  corrections: number;
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
