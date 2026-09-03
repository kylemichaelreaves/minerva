// Corpus facts derived from data rather than hand-typed into copy.
//
// The author/work/cross-reference COUNTS already come live from the
// backend (`fetchLandingStats` / the network summary). The corpus's
// time span, by contrast, used to be a hardcoded "2,400 years" pasted
// into four different strings — easy to forget and let drift. There's
// no author-date column in the DB (only chronological ranks in
// `author_ordering.py`), so the authoritative year data is the
// per-author years already curated in `atlasData.ts`. Derive the span
// from there so it updates whenever an earlier/later author is added.

import { ATLAS_AUTHORS } from "~/data/atlasData";

const YEARS = ATLAS_AUTHORS.map((a) => a.year);
const MIN_YEAR = Math.min(...YEARS);
const MAX_YEAR = Math.max(...YEARS);

/** Total span of the corpus in years, across every dated entry
 *  (Hebrew Bible → the latest edition), rounded to the nearest
 *  century. Replaces the old hardcoded "2,400". */
export const CORPUS_YEAR_SPAN = Math.round((MAX_YEAR - MIN_YEAR) / 100) * 100;

/** `CORPUS_YEAR_SPAN` with a thousands separator, e.g. "2,900". */
export const CORPUS_YEAR_SPAN_LABEL = CORPUS_YEAR_SPAN.toLocaleString();
