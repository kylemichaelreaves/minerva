import { apiGet, apiPost, qs } from "~/api/client";
import { cachedRead } from "~/api/readCache";
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
  /** Author SLUG. Disambiguates same-titled works (Luther 1912 vs 1545) —
   *  it is a path segment now, not a query parameter (#602). */
  authorSlug?: string;
  from?: number;
  limit?: number;
  around?: string;
  /** Scope the range to a specific edition (`e<id>`/`t<id>`); overrides
   * the default-edition resolution. From the edition switcher (#50). */
  edition?: string;
  /** Center the window on the first chunk with this section locator in
   * the target edition — preserves reading position across a switch. */
  at_section?: string;
}

export async function getWorkRange(
  workSlug: string,
  args: WorkRangeArgs = {},
  signal?: AbortSignal,
): Promise<WorkRange> {
  // `#/r/<authorSlug>/<titleSlug>` maps straight onto
  // `/api/works/<authorSlug>/<titleSlug>` (#602); the server resolves the pair
  // and returns the canonical author and title in the payload. Without an
  // author the one-segment form is sent, which the server also accepts.
  //
  // Cached: a route switch unmounts the Reader, and returning to it asks
  // for the same window again. See `readCache.ts`.
  const segments = args.authorSlug
    ? `${encodeURIComponent(args.authorSlug)}/${encodeURIComponent(workSlug)}`
    : encodeURIComponent(workSlug);
  const path = `/api/works/${segments}${qs({
    lang: args.lang,
    from: args.from,
    limit: args.limit,
    around: args.around,
    edition: args.edition,
    at_section: args.at_section,
  })}`;
  return cachedRead(path, () => apiGet<WorkRange>(path, signal));
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
  // Cached (see `readCache.ts`): fires alongside every work-range load, and
  // term occurrences are fixed for the session — the glossary is only
  // written by the CLI importer.
  const path = `/api/works/${workId}/occurrence_map${qs({
    lang: args.lang,
    from: args.from,
    limit: args.limit,
  })}`;
  return cachedRead(path, () => apiGet<OccurrenceMap>(path, signal));
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
