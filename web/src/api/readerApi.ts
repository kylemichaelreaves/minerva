import { apiGet, apiPost, qs } from "~/api/client";
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
  return apiGet<WorkRange>(
    `/api/works/${encodeURIComponent(work)}${qs({
      lang: args.lang,
      from: args.from,
      limit: args.limit,
      around: args.around,
    })}`,
    signal,
  );
}

export async function fetchChunkContext(
  chunkId: string,
  radius = 1,
  signal?: AbortSignal,
): Promise<ChunkContextResponse> {
  return apiGet<ChunkContextResponse>(
    `/api/chunks/${encodeURIComponent(chunkId)}/context${qs({
      radius: radius !== 1 ? radius : undefined,
    })}`,
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
  return apiGet<OccurrenceMap>(
    `/api/works/${workId}/occurrence_map${qs({
      lang: args.lang,
      from: args.from,
      limit: args.limit,
    })}`,
    signal,
  );
}

export async function fetchLemmaHighlights(
  workId: number,
  args: { lang?: string; from?: number; limit?: number; lemma: string },
  signal?: AbortSignal,
): Promise<LemmaHighlights> {
  return apiGet<LemmaHighlights>(
    `/api/works/${workId}/lemma_highlights${qs({
      lemma: args.lemma,
      lang: args.lang,
      from: args.from,
      limit: args.limit,
    })}`,
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
  return apiGet<WordLookup>(
    `/api/words/lookup${qs({
      chunk_id: chunkId,
      offset,
      samples_limit: args.samplesLimit,
      samples_offset: args.samplesOffset,
    })}`,
    signal,
  );
}
