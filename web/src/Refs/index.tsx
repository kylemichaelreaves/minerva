// Corpus-wide cross-references browser. Phase 5 deliverable.
// Infinite-scroll: first page of PAGE_SIZE rows lands via the
// useAbortableFetch hook below; an IntersectionObserver sentinel near
// the bottom of the list fetches further pages and concatenates them.

import { For, Show, createMemo, onMount } from "solid-js";
import {
  fetchReferencesList,
  fetchReferencesSources,
  type ReferencesListRow,
} from "~/api/refsApi";
import { LoadingDots } from "~/components/LoadingDots";
import { FilterSheet } from "~/components/FilterSheet";
import { useMobileShell } from "~/components/MobileShellContext";
import { useAbortableFetch } from "~/hooks/useAbortableFetch";
import { useInfiniteScrollSentinel } from "~/hooks/useInfiniteScrollSentinel";
import { usePaginatedAppend } from "~/hooks/usePaginatedAppend";
import { RefRow } from "~/Refs/components/RefRow";
import { RefsEmptyState } from "~/Refs/components/RefsEmptyState";
import { RefsFiltersBar } from "~/Refs/components/RefsFiltersBar";
import { RefsPageHeader } from "~/Refs/components/RefsPageHeader";
import {
  REFS_PAGE_SIZE,
  buildReferencesListArgs,
  mergeRefsNavigate,
  useRefsSourceAuthors,
} from "~/Refs/components/refsList";
import "~/Refs/refs.css";

const PAGE_SIZE = REFS_PAGE_SIZE;

export interface RefsProps {
  sourceAuthor?: string;
  targetAuthor?: string;
  targetWork?: string;
  referenceType?: string;
  includeRejected?: boolean;
  onNavigate: (filters: {
    sourceAuthor?: string;
    targetAuthor?: string;
    targetWork?: string;
    referenceType?: string;
    includeRejected?: boolean;
  }) => void;
  onOpenSource: (workTitle: string, chunkId: string) => void;
  onOpenReview?: () => void;
}

export default function Refs(props: RefsProps) {
  const shell = useMobileShell();

  onMount(() => {
    shell.registerSurfaceActions({
      openFilters: () => shell.setFiltersSheetOpen(true),
    });
  });

  const { data, loading, error } = useAbortableFetch(
    () =>
      buildReferencesListArgs({
        ...props,
        limit: PAGE_SIZE,
        offset: 0,
      }),
    fetchReferencesList,
  );

  const pagination = usePaginatedAppend<ReferencesListRow>(() => data());

  const firstPage = (): ReferencesListRow[] => data()?.references ?? [];
  const rows = (): ReferencesListRow[] => pagination.rows(firstPage());
  const total = (): number => data()?.total ?? 0;
  const hasMore = (): boolean =>
    pagination.hasMore(firstPage(), total());

  const fetchPage = (offset: number, signal: AbortSignal) =>
    fetchReferencesList(
      buildReferencesListArgs({ ...props, limit: PAGE_SIZE, offset }),
      signal,
    ).then((res) => ({ items: res.references }));

  const setSentinelEl = useInfiniteScrollSentinel(
    () => hasMore() && !loading(),
    () => {
      if (!hasMore() || pagination.appending()) return;
      void pagination.loadMore(firstPage(), fetchPage);
    },
  );

  const { data: sourcesData } = useAbortableFetch(
    () => ({ includeRejected: props.includeRejected }),
    fetchReferencesSources,
  );

  const sourceAuthors = useRefsSourceAuthors(sourcesData, () => data()?.references);
  const targetAuthors = createMemo<string[]>(() => {
    const fromEndpoint = sourcesData()?.targets;
    if (fromEndpoint && fromEndpoint.length > 0) return fromEndpoint;
    const set = new Set<string>();
    for (const r of data()?.references ?? []) {
      if (r.target.author) set.add(r.target.author);
    }
    return Array.from(set).sort();
  });

  const filtersBar = () => (
    <RefsFiltersBar
      sourceAuthor={props.sourceAuthor}
      targetAuthor={props.targetAuthor}
      referenceType={props.referenceType}
      includeRejected={props.includeRejected}
      sourceOptions={sourceAuthors()}
      targetOptions={targetAuthors()}
      onChange={(patch) => {
        props.onNavigate(mergeRefsNavigate({
          sourceAuthor: props.sourceAuthor,
          targetAuthor: props.targetAuthor,
          targetWork: props.targetWork,
          referenceType: props.referenceType,
          includeRejected: props.includeRejected,
        }, patch));
      }}
    />
  );

  return (
    <div class="refs-page">
      <RefsPageHeader
        title="Cross-references"
        loading={loading()}
        error={error() ? `Could not load references: ${error()}` : null}
        meta={
          <div class="refs-summary">
            <Show
              when={!loading() && data()}
              fallback={
                <Show when={loading()}>
                  <span class="refs-meta">
                    loading
                    <LoadingDots />
                  </span>
                </Show>
              }
            >
              <span class="refs-meta">
                {total().toLocaleString()} references
              </span>
            </Show>
            <Show when={props.onOpenReview}>
              <button
                class="refs-review-link"
                type="button"
                onClick={() => { props.onOpenReview?.(); }}
              >
                Review queue →
              </button>
            </Show>
          </div>
        }
      />

      <FilterSheet>{filtersBar()}</FilterSheet>

      <Show
        when={!loading() && data() && rows().length === 0}
      >
        <RefsEmptyState
          hasFilters={
            Boolean(props.sourceAuthor) ||
            Boolean(props.targetAuthor) ||
            Boolean(props.targetWork) ||
            Boolean(props.referenceType)
          }
          onClear={() =>
            { props.onNavigate({
              sourceAuthor: undefined,
              targetAuthor: undefined,
              targetWork: undefined,
              referenceType: undefined,
              includeRejected: false,
            }); }
          }
        />
      </Show>

      <ul class="refs-list">
        <For each={rows()}>
          {(row) => <RefRow row={row} onOpenSource={props.onOpenSource} />}
        </For>
      </ul>

      <Show when={hasMore() && !loading()}>
        <div class="refs-sentinel" ref={setSentinelEl}>
          <Show when={pagination.appending()} fallback={<span>&nbsp;</span>}>
            <span class="refs-meta">
              loading more
              <LoadingDots />
            </span>
          </Show>
        </div>
      </Show>

      <Show when={pagination.appendError()}>
        <div class="refs-error">
          Could not load more references: {pagination.appendError()}
        </div>
      </Show>
    </div>
  );
}
