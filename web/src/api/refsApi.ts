import { apiGet, apiPatch } from "~/api/client";
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
  const params = new URLSearchParams();
  if (args.lang) params.set("lang", args.lang);
  if (args.from !== undefined) params.set("from", String(args.from));
  if (args.limit !== undefined) params.set("limit", String(args.limit));
  const qs = params.toString();
  return apiGet<ReferencesMap>(
    `/api/works/${workId}/references_map${qs ? `?${qs}` : ""}`,
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
  const params = new URLSearchParams();
  if (args.sourceAuthor) params.set("source_author", args.sourceAuthor);
  if (args.targetAuthor) params.set("target_author", args.targetAuthor);
  if (args.targetWork) params.set("target_work", args.targetWork);
  if (args.referenceType) params.set("reference_type", args.referenceType);
  if (args.limit !== undefined) params.set("limit", String(args.limit));
  if (args.offset !== undefined) params.set("offset", String(args.offset));
  if (args.minConfidence !== undefined)
    params.set("min_confidence", String(args.minConfidence));
  if (args.includeRejected) params.set("include_rejected", "1");
  const qs = params.toString();
  return apiGet<ReferencesListResponse>(
    `/api/references${qs ? `?${qs}` : ""}`,
    signal,
  );
}

export async function fetchReferencesSources(
  args: { minConfidence?: number; includeRejected?: boolean } = {},
  signal?: AbortSignal,
): Promise<RefsSourcesResponse> {
  const params = new URLSearchParams();
  if (args.minConfidence !== undefined)
    params.set("min_confidence", String(args.minConfidence));
  if (args.includeRejected) params.set("include_rejected", "1");
  const qs = params.toString();
  return apiGet<RefsSourcesResponse>(
    `/api/references/sources${qs ? `?${qs}` : ""}`,
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
  const params = new URLSearchParams();
  if (args.limit !== undefined) params.set("limit", String(args.limit));
  if (args.offset !== undefined) params.set("offset", String(args.offset));
  if (args.sourceAuthor) params.set("source_author", args.sourceAuthor);
  if (args.referenceType) params.set("reference_type", args.referenceType);
  if (args.minConfidence !== undefined)
    params.set("min_confidence", String(args.minConfidence));
  if (args.maxConfidence !== undefined)
    params.set("max_confidence", String(args.maxConfidence));
  const qs = params.toString();
  return apiGet<ReviewQueueResponse>(
    `/api/references/review_queue${qs ? `?${qs}` : ""}`,
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
