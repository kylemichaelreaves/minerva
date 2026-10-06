import type { LemmaDetailResponse, LemmaIndexResponse } from "~/api/concordanceApi";

/** A minimal, well-formed /api/concordance/index response. One row, so a
 *  test that waits for the index can see it render (#761). */
export function makeLemmaIndex(over: Partial<LemmaIndexResponse> = {}): LemmaIndexResponse {
  return {
    scope: "corpus",
    scope_label: "the whole corpus",
    lang: "deu",
    letter: null,
    sort: "freq",
    total_lemmas: 1,
    total_occurrences: 12,
    letter_counts: { W: 1 },
    limit: 100,
    offset: 0,
    next_offset: null,
    rows: [{ rank: 1, lemma: "Ware", pos: "NOUN", count: 12, distinct_works: 1, per_work: [] }],
    ...over,
  };
}

/** A minimal, well-formed /api/concordance/lemma response: identity card
 *  totals and empty breakdowns, no KWIC rows (#761). */
export function makeLemmaDetail(over: Partial<LemmaDetailResponse> = {}): LemmaDetailResponse {
  return {
    lemma: "Ware",
    lang: "deu",
    scope: "corpus",
    scope_label: "the whole corpus",
    filters: { pos: null, morph: {}, surface: null },
    total: 12,
    limit: 50,
    offset: 0,
    pos_breakdown: [{ value: "NOUN", count: 12 }],
    case_breakdown: [],
    number_breakdown: [],
    gender_breakdown: [],
    surface_breakdown: [],
    work_breakdown: [],
    drop_counts: {},
    rows: [],
    next_offset: null,
    ...over,
  };
}
