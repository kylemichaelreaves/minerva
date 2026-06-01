import { createMemo } from "solid-js";
import type { ReferencesListRow } from "~/api/refsApi";
import type { SelectOption } from "~/components/Select";

export const REFS_PAGE_SIZE = 50;

export function stringsToSelectOptions(authors: string[]): SelectOption[] {
  return authors.map((a) => ({ value: a, label: a }));
}

export function buildReferencesListArgs(props: {
  sourceAuthor?: string;
  targetAuthor?: string;
  targetWork?: string;
  referenceType?: string;
  includeRejected?: boolean;
  limit: number;
  offset: number;
}) {
  return {
    sourceAuthor: props.sourceAuthor,
    targetAuthor: props.targetAuthor,
    targetWork: props.targetWork,
    referenceType: props.referenceType,
    includeRejected: props.includeRejected,
    limit: props.limit,
    offset: props.offset,
  };
}

export function mergeRefsNavigate<T extends Record<string, unknown>>(
  current: T,
  patch: Partial<T>,
): T {
  return { ...current, ...patch };
}

export function useRefsSourceAuthors(
  sourcesData: () => { sources?: string[] } | null | undefined,
  listRows: () => ReferencesListRow[] | undefined,
) {
  return createMemo<string[]>(() => {
    const fromEndpoint = sourcesData()?.sources;
    if (fromEndpoint && fromEndpoint.length > 0) return fromEndpoint;
    const set = new Set<string>();
    for (const r of listRows() ?? []) {
      if (r.source.author) set.add(r.source.author);
    }
    return Array.from(set).sort();
  });
}
