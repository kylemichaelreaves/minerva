import type {
  AuthorPair,
  MatrixCell,
  NetworkAuthor,
  NetworkSummary,
  TopWorkRow,
} from "~/api/networkApi";

/** A minimal, well-formed NetworkSummary for Network surface tests. Every
 *  list defaults to empty so a test only spells out what it asserts on. */
export function makeNetworkSummary(
  over: {
    xrefs?: number;
    authors?: NetworkAuthor[];
    /** Matrix cells; the matrix panel only draws authors that appear in one. */
    cells?: MatrixCell[];
    pairs?: AuthorPair[];
    works?: TopWorkRow[];
  } = {},
): NetworkSummary {
  const authors = over.authors ?? [];
  return {
    totals: { xrefs: over.xrefs ?? 0, authors: authors.length, works: 0 },
    matrix: { authors, cells: over.cells ?? [] },
    top_pairs: { all: over.pairs ?? [], non_scrip: over.pairs ?? [], per_author_top: [] },
    scripture_heatmap: { authors: [], sections: [], cells: [] },
    verification: [],
    top_works: over.works ?? [],
    apparatus_sources: [],
  };
}
