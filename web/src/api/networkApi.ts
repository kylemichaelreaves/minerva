import { apiGet } from "~/api/client";

export type CorpusBucket = "scrip" | "class" | "med" | "em" | "mod" | "ext";

export interface NetworkAuthor {
  name: string;
  short: string;
  ord: number;
  corpus: CorpusBucket;
}

export interface MatrixCell {
  r: number;
  c: number;
  n: number;
}

export interface AuthorPair {
  src: string;
  tgt: string;
  n: number;
  intra_scrip: boolean;
}

export interface HeatmapCell {
  author: string;
  book: string;
  n: number;
}

export interface HeatmapSection {
  name: string;
  books: string[];
}

export interface VerificationRow {
  author: string;
  total: number;
  parts: {
    manual: number;
    rule_strong: number;
    "rule+embed": number;
    "rule+embed+llm": number;
    rule_weak: number;
  };
  other: number;
}

export interface TopWorkRow {
  work: string;
  author: string;
  n: number;
}

export interface NetworkSummary {
  totals: { xrefs: number; authors: number; works: number };
  matrix: { authors: NetworkAuthor[]; cells: MatrixCell[] };
  top_pairs: {
    all: AuthorPair[];
    non_scrip: AuthorPair[];
    /** Top 3 outgoing non-intra-scripture pairs per source author —
     *  guarantees Hegel→Heraclitus / Nietzsche→Heraclitus and other
     *  canonical-lineage edges survive the volume-rank truncation
     *  used by ``non_scrip``. The arc panel unions both. */
    per_author_top: AuthorPair[];
  };
  scripture_heatmap: {
    authors: string[];
    sections: HeatmapSection[];
    cells: HeatmapCell[];
  };
  verification: VerificationRow[];
  top_works: TopWorkRow[];
}

export interface NetworkSummaryArgs {
  minConfidence?: number;
  includeRejected?: boolean;
  sourceAuthors?: string[];
  corpora?: string[];
  sourceMethods?: string[];
}

export async function fetchNetworkSummary(
  args: NetworkSummaryArgs,
  signal?: AbortSignal,
): Promise<NetworkSummary> {
  const params = new URLSearchParams();
  if (args.minConfidence !== undefined)
    params.set("min_confidence", String(args.minConfidence));
  if (args.includeRejected) params.set("include_rejected", "1");
  if (args.sourceAuthors?.length)
    params.set("source_author", args.sourceAuthors.join(","));
  if (args.corpora?.length) params.set("corpus", args.corpora.join(","));
  if (args.sourceMethods?.length)
    params.set("source_method", args.sourceMethods.join(","));
  const qs = params.toString();
  return apiGet<NetworkSummary>(`/api/network/summary${qs ? `?${qs}` : ""}`, signal);
}
