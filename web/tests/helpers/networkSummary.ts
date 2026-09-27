import type { AuthorPair, NetworkAuthor, NetworkSummary, TopWorkRow } from "~/api/networkApi";

/** A minimal, well-formed NetworkSummary for Network surface tests. Every
 *  list defaults to empty so a test only spells out what it asserts on. */
export function makeNetworkSummary(
  over: {
    xrefs?: number;
    authors?: NetworkAuthor[];
    pairs?: AuthorPair[];
    works?: TopWorkRow[];
  } = {},
): NetworkSummary {
  const authors = over.authors ?? [];
  return {
    totals: { xrefs: over.xrefs ?? 0, authors: authors.length, works: 0 },
    matrix: { authors, cells: [] },
    top_pairs: { all: over.pairs ?? [], non_scrip: over.pairs ?? [], per_author_top: [] },
    scripture_heatmap: { authors: [], sections: [], cells: [] },
    verification: [],
    top_works: over.works ?? [],
  };
}
