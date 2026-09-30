// Concordance API client.
// Backend: src/minerva/concordance/queries.py
//   /api/concordance/index?lang=deu&scope=corpus&letter=A&sort=freq
//   /api/concordance/lemma?lemma=Geist&lang=deu&scope=work&work=…

import { apiGet, qs } from "~/api/client";

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
  /** Lemmas in scope, ignoring the frequency range — orientation, NOT a row
   *  count. Do not paginate on it; use `next_offset` (#371). */
  total_lemmas: number;
  total_occurrences: number;
  /** Rows per A–Z rail letter, over the whole filtered scope (#376). Keyed by
   *  the same folded initial the `letter` filter matches on, so a present key
   *  means clicking that letter returns rows. Computed WITHOUT the letter
   *  filter — the rail must keep showing where else there is something while
   *  one letter is selected — and WITH the frequency range, unlike
   *  `total_lemmas`. Letters with nothing in scope are absent, not zero. */
  letter_counts: Record<string, number>;
  limit: number;
  offset: number;
  /** Offset of the next page, or null when this was the last one. Derived
   *  server-side from the rows actually returned. */
  next_offset: number | null;
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
  /** Per requested morph feature (`Case`, `Number`, …): the total this
   *  request would return with that one feature's filter removed and
   *  every other filter kept. What the empty state's "Drop X · N hits"
   *  links promise; no breakdown can supply it (#691). */
  drop_counts: Record<string, number>;
  rows: KwicRow[];
  next_offset: number | null;
}

export interface LemmaIndexArgs {
  lang: string;
  scope?: ConcScope;
  /** Selected author names for scope=author (or the work-picker
   *  narrowing filter). Multiple authors are sent to the backend joined
   *  by a literal TAB in the `author` query param. */
  authors?: string[];
  /** Selected work titles for scope=work. Multiple works are sent to
   *  the backend joined by a literal TAB in the `work` query param. */
  works?: string[];
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
  /** Selected author names for scope=author. Multiple authors are sent
   *  to the backend joined by a literal TAB in the `author` query param. */
  authors?: string[];
  /** Selected work titles for scope=work. Multiple works are sent to
   *  the backend joined by a literal TAB in the `work` query param. */
  works?: string[];
  pos?: string;
  morph?: Record<string, string>;
  surface?: string;
  limit?: number;
  offset?: number;
}

export async function fetchLemmaIndex(
  args: LemmaIndexArgs,
  signal?: AbortSignal,
): Promise<LemmaIndexResponse> {
  return apiGet<LemmaIndexResponse>(
    `/api/concordance/index${qs({
      lang: args.lang,
      scope: args.scope,
      // Multiple authors → single `author` param, TAB-joined; qs()
      // URL-encodes the value so the tab travels safely. Omit when empty.
      author: args.authors?.length ? args.authors.join("\t") : undefined,
      // Multiple works → single `work` param, TAB-joined; qs() URL-encodes
      // the value so the tab travels safely. Omit when empty.
      work: args.works?.length ? args.works.join("\t") : undefined,
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
    `/api/concordance/lemma${qs({
      lemma: args.lemma,
      lang: args.lang,
      scope: args.scope,
      author: args.authors?.length ? args.authors.join("\t") : undefined,
      work: args.works?.length ? args.works.join("\t") : undefined,
      pos: args.pos,
      morph,
      surface: args.surface,
      limit: args.limit,
      offset: args.offset,
    })}`,
    signal,
  );
}
