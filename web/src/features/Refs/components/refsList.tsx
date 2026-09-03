import { createMemo } from "solid-js";
import type { ReferencesListRow } from "~/api/refsApi";
import type { SelectOption } from "~/components/primitives/Select";

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

// `Array.prototype.sort()` with no comparator orders by UTF-16 code unit,
// which files every accented capital after `Z` — `Épictète` (U+00C9) would
// sort past `Zénon`. The locale is pinned rather than left to the runtime so
// the order does not depend on the machine's LANG; the UI is English.
function byAuthorName(a: string, b: string): number {
  return a.localeCompare(b, "en");
}

// Shared by both author dropdowns. The endpoint's own ordering is authoritative
// when it supplies one — for sources that ordering is CHRONOLOGICAL
// (`author_sort_key`, src/minerva/refs/list_queries.py), not alphabetical, so
// re-sorting it here would silently override the server. The fallback only
// runs when the endpoint returns nothing.
function useAuthorOptions(
  fromEndpoint: () => string[] | undefined,
  fromRows: () => (string | null)[],
) {
  // Captured in a local rather than returned inline so
  // eslint-plugin-solid can see the memo's identity.
  const authors = createMemo<string[]>(() => {
    const supplied = fromEndpoint();
    if (supplied && supplied.length > 0) return supplied;
    const set = new Set<string>();
    for (const author of fromRows()) {
      if (author) set.add(author);
    }
    return Array.from(set).sort(byAuthorName);
  });
  return authors;
}

export function useRefsSourceAuthors(
  sourcesData: () => { sources?: string[] } | null | undefined,
  listRows: () => ReferencesListRow[] | undefined,
) {
  return useAuthorOptions(
    () => sourcesData()?.sources,
    () => (listRows() ?? []).map((r) => r.source.author),
  );
}

export function useRefsTargetAuthors(
  sourcesData: () => { targets?: string[] } | null | undefined,
  listRows: () => ReferencesListRow[] | undefined,
) {
  return useAuthorOptions(
    () => sourcesData()?.targets,
    () => (listRows() ?? []).map((r) => r.target.author),
  );
}
