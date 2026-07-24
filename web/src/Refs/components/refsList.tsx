import { createMemo } from "solid-js";
import type { ReferencesListRow } from "~/api/refsApi";
import type { SelectOption } from "~/components/Select";

export const REFS_PAGE_SIZE = 50;

export function stringsToSelectOptions(authors: string[]): SelectOption[] {
  return authors.map((a) => ({ value: a, label: a }));
}

// The parameter is deliberately NOT named `props`: this is a plain mapping
// helper, not a component, and callers already invoke it inside a tracked
// scope (see the `useAbortableFetch` source thunk in ../index.tsx). Naming it
// `props` made eslint-plugin-solid's reactivity heuristic report every field
// read as an untracked access — seven false positives that buried the real
// reactivity warnings elsewhere in the tree.
export function buildReferencesListArgs(filters: {
  sourceAuthor?: string;
  targetAuthor?: string;
  targetWork?: string;
  referenceType?: string;
  includeRejected?: boolean;
  limit: number;
  offset: number;
}) {
  return {
    sourceAuthor: filters.sourceAuthor,
    targetAuthor: filters.targetAuthor,
    targetWork: filters.targetWork,
    referenceType: filters.referenceType,
    includeRejected: filters.includeRejected,
    limit: filters.limit,
    offset: filters.offset,
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
  // Captured in a local rather than returned inline so
  // eslint-plugin-solid can see the memo's identity.
  const authors = createMemo<string[]>(() => {
    const fromEndpoint = sourcesData()?.sources;
    if (fromEndpoint && fromEndpoint.length > 0) return fromEndpoint;
    const set = new Set<string>();
    for (const r of listRows() ?? []) {
      if (r.source.author) set.add(r.source.author);
    }
    return Array.from(set).sort();
  });
  return authors;
}
