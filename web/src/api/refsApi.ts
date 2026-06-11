import { apiGet, apiPatch, qs } from "~/api/client";
import type {
  Reference,
  ReferencesListResponse,
  ReferencesMap,
  RefsSourcesResponse,
  ReviewQueueResponse,
} from "~/api/types/refs";

export type {
  Reference,
  ReferenceTarget,
  ReferenceType,
  ReferencesListResponse,
  ReferencesListRow,
  ReferencesMap,
  RefsSourcesResponse,
  ReviewQueueResponse,
  ReviewQueueRow,
} from "~/api/types/refs";

export async function fetchReferencesMap(
  workId: number,
  args: { lang?: string; from?: number; limit?: number } = {},
  signal?: AbortSignal,
): Promise<ReferencesMap> {
  return apiGet<ReferencesMap>(
    `/api/works/${workId}/references_map${qs({
      lang: args.lang,
      from: args.from,
      limit: args.limit,
    })}`,
    signal,
  );
}

export async function fetchReferencesList(
  args: {
    sourceAuthor?: string;
    targetAuthor?: string;
    targetWork?: string;
    referenceType?: string;
    limit?: number;
    offset?: number;
    minConfidence?: number;
    includeRejected?: boolean;
  } = {},
  signal?: AbortSignal,
): Promise<ReferencesListResponse> {
  return apiGet<ReferencesListResponse>(
    `/api/references${qs({
      source_author: args.sourceAuthor,
      target_author: args.targetAuthor,
      target_work: args.targetWork,
      reference_type: args.referenceType,
      limit: args.limit,
      offset: args.offset,
      min_confidence: args.minConfidence,
      include_rejected: args.includeRejected,
    })}`,
    signal,
  );
}

export async function fetchReferencesSources(
  args: { minConfidence?: number; includeRejected?: boolean } = {},
  signal?: AbortSignal,
): Promise<RefsSourcesResponse> {
  return apiGet<RefsSourcesResponse>(
    `/api/references/sources${qs({
      min_confidence: args.minConfidence,
      include_rejected: args.includeRejected,
    })}`,
    signal,
  );
}

export async function fetchReviewQueue(
  args: {
    limit?: number;
    offset?: number;
    sourceAuthor?: string;
    referenceType?: string;
    minConfidence?: number;
    maxConfidence?: number;
  } = {},
  signal?: AbortSignal,
): Promise<ReviewQueueResponse> {
  return apiGet<ReviewQueueResponse>(
    `/api/references/review_queue${qs({
      limit: args.limit,
      offset: args.offset,
      source_author: args.sourceAuthor,
      reference_type: args.referenceType,
      min_confidence: args.minConfidence,
      max_confidence: args.maxConfidence,
    })}`,
    signal,
  );
}

export async function updateReferenceCuration(
  id: number,
  patch: {
    curator_status: "approved" | "rejected" | "auto" | "manual";
    curator_note?: string | null;
  },
  signal?: AbortSignal,
): Promise<Reference> {
  return apiPatch<Reference>(`/api/references/${id}`, patch, signal);
}
