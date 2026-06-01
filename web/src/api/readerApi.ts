import { apiGet, apiPost } from "~/api/client";
import type {
  ChunkContextResponse,
  LemmaHighlights,
  OccurrenceMap,
  TargetLang,
  TermDetail,
  TranslationResponse,
  WordLookup,
  Work,
  WorkRange,
} from "~/api/types/reader";

export async function listWorks(signal?: AbortSignal): Promise<Work[]> {
  const body = await apiGet<{ works?: Work[] }>("/api/works", signal);
  return body.works ?? [];
}

export interface WorkRangeArgs {
  lang?: string;
  from?: number;
  limit?: number;
  around?: string;
}

export async function getWorkRange(
  work: string,
  args: WorkRangeArgs = {},
  signal?: AbortSignal,
): Promise<WorkRange> {
  const params = new URLSearchParams();
  if (args.lang) params.set("lang", args.lang);
  if (args.from !== undefined) params.set("from", String(args.from));
  if (args.limit !== undefined) params.set("limit", String(args.limit));
  if (args.around) params.set("around", args.around);
  const qs = params.toString();
  return apiGet<WorkRange>(
    `/api/works/${encodeURIComponent(work)}${qs ? `?${qs}` : ""}`,
    signal,
  );
}

export async function fetchChunkContext(
  chunkId: string,
  radius = 1,
  signal?: AbortSignal,
): Promise<ChunkContextResponse> {
  const params = new URLSearchParams();
  if (radius !== 1) params.set("radius", String(radius));
  const qs = params.toString();
  return apiGet<ChunkContextResponse>(
    `/api/chunks/${encodeURIComponent(chunkId)}/context${qs ? `?${qs}` : ""}`,
    signal,
  );
}

export async function translate(
  source_text: string,
  target_lang: TargetLang,
  signal?: AbortSignal,
): Promise<TranslationResponse> {
  return apiPost<TranslationResponse>(
    "/api/translate",
    { source_text, target_lang },
    signal,
  );
}

export async function fetchOccurrenceMap(
  workId: number,
  args: { lang?: string; from?: number; limit?: number } = {},
  signal?: AbortSignal,
): Promise<OccurrenceMap> {
  const params = new URLSearchParams();
  if (args.lang) params.set("lang", args.lang);
  if (args.from !== undefined) params.set("from", String(args.from));
  if (args.limit !== undefined) params.set("limit", String(args.limit));
  const qs = params.toString();
  return apiGet<OccurrenceMap>(
    `/api/works/${workId}/occurrence_map${qs ? `?${qs}` : ""}`,
    signal,
  );
}

export async function fetchLemmaHighlights(
  workId: number,
  args: { lang?: string; from?: number; limit?: number; lemma: string },
  signal?: AbortSignal,
): Promise<LemmaHighlights> {
  const params = new URLSearchParams({ lemma: args.lemma });
  if (args.lang) params.set("lang", args.lang);
  if (args.from !== undefined) params.set("from", String(args.from));
  if (args.limit !== undefined) params.set("limit", String(args.limit));
  return apiGet<LemmaHighlights>(
    `/api/works/${workId}/lemma_highlights?${params.toString()}`,
    signal,
  );
}

export async function fetchTermDetail(
  termId: number,
  signal?: AbortSignal,
): Promise<TermDetail> {
  return apiGet<TermDetail>(`/api/terms/${termId}`, signal);
}

export interface WordLookupArgs {
  samplesLimit?: number;
  samplesOffset?: number;
}

export async function fetchWordLookup(
  chunkId: string,
  offset: number,
  args: WordLookupArgs = {},
  signal?: AbortSignal,
): Promise<WordLookup> {
  const params = new URLSearchParams({
    chunk_id: chunkId,
    offset: String(offset),
  });
  if (args.samplesLimit !== undefined) {
    params.set("samples_limit", String(args.samplesLimit));
  }
  if (args.samplesOffset !== undefined) {
    params.set("samples_offset", String(args.samplesOffset));
  }
  return apiGet<WordLookup>(`/api/words/lookup?${params.toString()}`, signal);
}
