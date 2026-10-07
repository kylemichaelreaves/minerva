/** Wire types for cross-reference endpoints. */

export interface ReferenceTarget {
  author: string;
  work: string;
  in_corpus_work_id: number | null;
  chunk_id: string | null;
  locator: string | null;
  locator_payload: Record<string, unknown> | null;
  sort_key: string | null;
}

export type ReferenceType =
  | "cites"
  | "quotes"
  | "paraphrases"
  | "alludes"
  | "comments_on"
  | "translates"
  | "disputes"
  | "corrects";

export interface Reference {
  id: number;
  source_chunk_id: string;
  source_span_start: number | null;
  source_span_end: number | null;
  source_form: string | null;
  quoted_phrase: string | null;
  target: ReferenceTarget;
  reference_type: ReferenceType;
  confidence: number;
  source_method: string;
  curator_status: "auto" | "approved" | "rejected" | "manual";
  /** Who decided the row (#718). NULL = unrecorded — most rejections
   *  predate migration 0039 — never "machine" (#720). */
  curated_by: "human" | "llm" | "embed" | null;
  curated_at: string | null;
  note: string | null;
}

export interface ReferencesMap {
  work_id: number;
  lang: string;
  from: number;
  limit: number;
  by_chunk: Record<string, { count: number; top: Reference[] }>;
}

export interface ReferencesListRow extends Reference {
  source: {
    author: string | null;
    work: string | null;
    section: string | null;
  };
}

export interface ReferencesListResponse {
  limit: number;
  offset: number;
  total: number;
  filters: {
    source_author: string | null;
    target_author: string | null;
    target_work: string | null;
    reference_type: string | null;
  };
  references: ReferencesListRow[];
}

export interface RefsSourcesResponse {
  sources: string[];
  targets: string[];
}

export interface ReviewQueueRow extends ReferencesListRow {
  source: {
    author: string | null;
    work: string | null;
    section: string | null;
    text: string | null;
  };
}

export interface ReviewQueueResponse {
  limit: number;
  offset: number;
  total_pending: number;
  references: ReviewQueueRow[];
}
