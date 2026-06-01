/** Wire types for concordance endpoints. */

export type ConcScope = "corpus" | "author" | "work";
export type ConcSort = "count" | "lemma";

export interface LemmaIndexRow {
  rank: number;
  lemma: string;
  pos: string;
  count: number;
  distinct_works: number;
  per_work: Array<{ work: string; count: number }>;
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
