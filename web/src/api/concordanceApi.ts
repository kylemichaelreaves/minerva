// Concordance API client.
// Backend: src/minerva/concordance/queries.py
//   /api/concordance/index?lang=deu&scope=corpus&letter=A&sort=freq
//   /api/concordance/lemma?lemma=Geist&lang=deu&scope=work&work=…

import { apiGet } from "~/api/client";

export type ConcScope = "corpus" | "author" | "work";
export type ConcSort = "freq" | "alpha" | "pos";

const CONC_SORTS: readonly ConcSort[] = ["freq", "alpha", "pos"];

export function isConcSort(v: string): v is ConcSort {
  return (CONC_SORTS as readonly string[]).includes(v);
}

export interface PerWorkBucket {
  work: string;
  n: number;
}

export interface LemmaIndexRow {
  rank: number;
  lemma: string;
  pos: string;
  count: number;
  distinct_works: number;
  per_work: PerWorkBucket[];
}

export interface LemmaIndexResponse {
  scope: ConcScope;
  scope_label: string;
  lang: string;
  letter: string | null;
  sort: ConcSort;
  total_lemmas: number;
  total_occurrences: number;
  limit: number;
  offset: number;
  rows: LemmaIndexRow[];
}

export interface BreakdownBucket {
  value: string;
  count: number;
}

export interface KwicRow {
  chunk_id: string;
  section: string;
  book: string;
  work: string;
  author: string;
  ord: number;
  surface: string;
  pos: string;
  morph: Record<string, string>;
  morph_str: string;
  kwic_left: string;
  kwic_match: string;
  kwic_right: string;
}

export interface LemmaDetailResponse {
  lemma: string;
  lang: string;
  scope: ConcScope;
  scope_label: string;
  filters: {
    pos: string | null;
    morph: Record<string, string>;
    surface: string | null;
  };
  total: number;
  limit: number;
  offset: number;
  pos_breakdown: BreakdownBucket[];
  case_breakdown: BreakdownBucket[];
  number_breakdown: BreakdownBucket[];
  gender_breakdown: BreakdownBucket[];
  surface_breakdown: BreakdownBucket[];
  work_breakdown: BreakdownBucket[];
  rows: KwicRow[];
  next_offset: number | null;
}

export interface LemmaIndexArgs {
  lang: string;
  scope?: ConcScope;
  author?: string;
  work?: string;
  letter?: string;
  sort?: ConcSort;
  limit?: number;
  offset?: number;
  /** Comma-separated UD POS whitelist (e.g. ``NOUN,VERB``). Backend
   *  default is content words only; pass ``"all"`` to surface
   *  function words too. */
  pos_in?: string;
  /** Lower edge of the frequency-range slider — drop lemmas under this
   *  many occurrences. */
  min_count?: number;
  /** Upper edge of the frequency-range slider. */
  max_count?: number;
  /** Lemma substring search (case-insensitive). */
  q?: string;
}

export interface LemmaDetailArgs {
  lemma: string;
  lang: string;
  scope?: ConcScope;
  author?: string;
  work?: string;
  pos?: string;
  morph?: Record<string, string>;
  surface?: string;
  limit?: number;
  offset?: number;
}

function _qs(params: Record<string, string | number | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === "") continue;
    u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

export async function fetchLemmaIndex(
  args: LemmaIndexArgs,
  signal?: AbortSignal,
): Promise<LemmaIndexResponse> {
  return apiGet<LemmaIndexResponse>(
    `/api/concordance/index${_qs({
      lang: args.lang,
      scope: args.scope,
      author: args.author,
      work: args.work,
      letter: args.letter,
      sort: args.sort,
      limit: args.limit,
      offset: args.offset,
      pos_in: args.pos_in,
      min_count: args.min_count,
      max_count: args.max_count,
      q: args.q,
    })}`,
    signal,
  );
}

export async function fetchLemmaDetail(
  args: LemmaDetailArgs,
  signal?: AbortSignal,
): Promise<LemmaDetailResponse> {
  const morph = args.morph
    ? Object.entries(args.morph)
        .map(([k, v]) => `${k}=${v}`)
        .join(",")
    : undefined;
  return apiGet<LemmaDetailResponse>(
    `/api/concordance/lemma${_qs({
      lemma: args.lemma,
      lang: args.lang,
      scope: args.scope,
      author: args.author,
      work: args.work,
      pos: args.pos,
      morph,
      surface: args.surface,
      limit: args.limit,
      offset: args.offset,
    })}`,
    signal,
  );
}
