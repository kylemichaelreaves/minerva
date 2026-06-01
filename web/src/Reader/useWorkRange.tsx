// Hook: load a windowed range of a work + its companion maps,
// with infinite-scroll pagination.
//
// Carved out of `Reader/index.tsx` per the maintainability audit; the
// loadWork pipeline (range fetch → occurrence-map + references-map
// companions → scroll-to-focus) was the single largest discrete
// block in the orchestrator. Pulling it here lets the Reader's main
// file stay focused on the rail / toolbar / card state machines.
//
// The hook owns:
//   * an internal AbortController for cancellable work-switching
//   * an aggregate `range` signal that GROWS as `loadMore` is called
//   * the four signals the orchestrator reads (range, occMap,
//     refsMap, loadError) PLUS `loadMore` / `hasMore` / `loadingMore`
//     for the pagination control surface
// The caller provides `props` (with workId / sourceLang /
// focusChunkId) and a `getStage` accessor so the hook can scroll the
// focused chunk into view after paint.
//
// Pagination model: on mount, fetch a first page (``PAGE_SIZE``
// chunks) — small enough that long works (Phil of Right body + notes
// = 586 chunks; Lectures on World History = 480) don't slam the
// network on initial render. As the reader scrolls toward the
// bottom, the Reader component calls ``loadMore()`` and the hook
// fetches the next page and APPENDS it to ``range().chunks``.
// Companion maps (occurrence + refs) are extended in lockstep so
// term-marker / xref-gutter affordances paint correctly for the
// newly-revealed chunks too.
//
// Focus mode (``around=<chunk_id>``) bypasses pagination — the
// reader centers a fixed window on the focused chunk and doesn't
// extend on scroll, so deep-links from citations remain stable.
//
// Last-write-wins guard: rapid navigation between works could let an
// older `getWorkRange` resolve after a newer one. We track which
// AbortController is current and discard responses whose controller
// has been replaced.

import {
  createEffect,
  createSignal,
  onCleanup,
  type Accessor,
} from "solid-js";
import { fetchOccurrenceMap, getWorkRange } from "~/api/readerApi";
import { fetchReferencesMap } from "~/api/refsApi";
import { errorMessage, isAbortError } from "~/utils/util";
import type {
  OccurrenceMap,
  ReferencesMap,
  WorkRange,
} from "~/utils/types";

export interface UseWorkRangeProps {
  workId: string;
  sourceLang?: string;
  focusChunkId?: string;
}

export interface UseWorkRangeResult {
  range: Accessor<WorkRange | null>;
  occMap: Accessor<OccurrenceMap | null>;
  refsMap: Accessor<ReferencesMap | null>;
  loadError: Accessor<string | null>;
  /** Fetches the next page and appends it to ``range().chunks``.
   *  No-op when there's nothing more to load, when a load is
   *  already in-flight, or when the reader is in focus-around
   *  mode (those windows are fixed). */
  loadMore: () => Promise<void>;
  /** ``true`` when more chunks are available beyond what's already
   *  loaded. Drives the sentinel's IntersectionObserver in the
   *  Reader component. */
  hasMore: Accessor<boolean>;
  /** ``true`` while a ``loadMore`` request is in flight. Lets the
   *  Reader render a small "loading more…" affordance and prevent
   *  rapid re-triggers from the IntersectionObserver. */
  loadingMore: Accessor<boolean>;
}

// First-page window size. 80 fills ~3 screens of typical reader
// density (one chunk ≈ 8-15 lines). Smaller than the prior 200
// default so initial paint is faster for long works; the user just
// scrolls and the next page streams in.
const PAGE_SIZE = 80;

// Focus-around window: when deep-linking from a citation, center
// the chunk in a wider window so the user has reading context above
// and below without needing to scroll-load. Stays the same as the
// old default since it's a one-shot fetch.
const FOCUS_WINDOW = 200;

export function useWorkRange(
  props: UseWorkRangeProps,
  getStage: () => HTMLDivElement | undefined,
): UseWorkRangeResult {
  const [range, setRange] = createSignal<WorkRange | null>(null);
  const [occMap, setOccMap] = createSignal<OccurrenceMap | null>(null);
  const [refsMap, setRefsMap] = createSignal<ReferencesMap | null>(null);
  const [loadError, setLoadError] = createSignal<string | null>(null);
  const [loadingMore, setLoadingMore] = createSignal(false);

  // Cancellation controller for the currently-active work. We
  // reuse it across the initial load AND every ``loadMore`` page
  // fetch so a work-switch via ``workId`` reactivity aborts both
  // the in-flight initial load AND any pagination request that's
  // mid-flight. The controller is rotated on each new ``loadWork``
  // call; the closure inside ``loadMore`` snapshots the current
  // reference and drops responses whose controller has since been
  // replaced. (This was the bug behind the 2026-05-30 race: when
  // ``loadWork`` cleared ``workController`` in its finally block,
  // a subsequent ``loadMore`` had no controller to inherit and
  // created a fresh one, untracked — a work-switch couldn't abort
  // it.)
  let workController: AbortController | undefined;
  // Track whether we're in focus-around mode (no pagination then).
  let focusMode = false;

  const hasMore = (): boolean => {
    if (focusMode) return false;
    const r = range();
    if (r === null) return false;
    return r.chunks.length < r.total;
  };

  /** Merge a freshly-fetched companion map's by_chunk entries into
   *  the existing map. The existing map's other fields stay (work_id,
   *  lang, from, limit); only by_chunk grows. ``loadMore`` always
   *  fetches strictly later chunks so by_chunk keys never overlap. */
  function _extendOccMap(extra: OccurrenceMap): void {
    setOccMap((prev) =>
      prev === null
        ? extra
        : {
            ...prev,
            by_chunk: { ...prev.by_chunk, ...extra.by_chunk },
          },
    );
  }
  function _extendRefsMap(extra: ReferencesMap): void {
    setRefsMap((prev) =>
      prev === null
        ? extra
        : {
            ...prev,
            by_chunk: { ...prev.by_chunk, ...extra.by_chunk },
          },
    );
  }

  async function _fetchCompanionMaps(
    workIdNum: number,
    lang: string,
    from: number,
    limit: number,
    controller: AbortController,
  ): Promise<void> {
    // Both companions fire in parallel; failures are silent (term
    // markers + xref gutter are non-essential affordances). Same
    // controller as the page fetch so a work-switch aborts both.
    void (async () => {
      try {
        const map = await fetchOccurrenceMap(
          workIdNum,
          { lang, from, limit },
          controller.signal,
        );
        if (!controller.signal.aborted) _extendOccMap(map);
      } catch (err) {
        if (isAbortError(err)) return;
      }
    })();
    void (async () => {
      try {
        const map = await fetchReferencesMap(
          workIdNum,
          { lang, from, limit },
          controller.signal,
        );
        if (!controller.signal.aborted) _extendRefsMap(map);
      } catch (err) {
        if (isAbortError(err)) return;
      }
    })();
  }

  async function loadWork() {
    // Cancel the previous in-flight load — rapid navigation between
    // works could otherwise let an older getWorkRange complete after
    // a newer one and clobber `range()` with stale chunks.
    workController?.abort();
    const controller = new AbortController();
    workController = controller;
    setLoadError(null);
    setRange(null);
    setOccMap(null);
    setRefsMap(null);
    setLoadingMore(false);
    focusMode = Boolean(props.focusChunkId);

    try {
      const r = await getWorkRange(
        props.workId,
        {
          lang: props.sourceLang ?? "grc",
          ...(props.focusChunkId
            ? { around: props.focusChunkId, limit: FOCUS_WINDOW }
            : { from: 0, limit: PAGE_SIZE }),
        },
        controller.signal,
      );
      // Last-write-wins guard: another loadWork may have started and
      // installed itself as `workController` between our fetch and
      // this resume. If so, drop the result silently.
      if (workController !== controller) return;
      setRange(r);

      // Kick off companion maps for the same window.
      _fetchCompanionMaps(r.work_id, r.lang, r.offset, r.limit, controller);

      // After paint, scroll the focused chunk into view.
      if (props.focusChunkId) {
        queueMicrotask(() => {
          const stage = getStage();
          if (!stage) return;
          const el = stage.querySelector(
            `[data-chunk-id="${CSS.escape(props.focusChunkId!)}"]`,
          );
          if (el) {
            el.scrollIntoView({ block: "center", behavior: "smooth" });
            el.classList.add("focused");
            window.setTimeout(() => {
              el.classList.remove("focused");
            }, 2400);
          }
        });
      }
    } catch (err) {
      if (isAbortError(err)) return;
      if (workController !== controller) return;
      const msg = errorMessage(err);
      setLoadError(msg);
    }
    // NOTE: we deliberately do NOT clear ``workController`` here.
    // ``loadMore`` reuses it so a later work-switch can abort both
    // initial load and pagination via a single ``.abort()``. The
    // controller is replaced (not cleared) in the next ``loadWork``
    // call's first line.
  }

  async function loadMore(): Promise<void> {
    // Bail-out gates. Each one has a load-bearing reason:
    //   * No range yet — initial load hasn't completed.
    //   * focusMode — citation deep-links use a fixed window.
    //   * loadingMore — IntersectionObserver fires repeatedly while
    //     the sentinel is visible; we want one request at a time.
    //   * hasMore false — all chunks already loaded.
    const cur = range();
    if (cur === null) return;
    if (focusMode) return;
    if (loadingMore()) return;
    if (cur.chunks.length >= cur.total) return;

    // Reuse the active work's controller — a work-switch via
    // ``loadWork`` will replace it and abort this fetch. If no
    // controller is present (shouldn't happen post-loadWork since
    // we no longer clear it in the finally block, but defensive),
    // synthesise one and track it so a switch still cancels.
    if (workController === undefined) {
      workController = new AbortController();
    }
    const controller = workController;
    setLoadingMore(true);
    try {
      const next = await getWorkRange(
        props.workId,
        {
          lang: cur.lang,
          from: cur.chunks.length,
          limit: PAGE_SIZE,
        },
        controller.signal,
      );
      // Work-switch may have happened mid-flight; drop the response
      // when the controller has been swapped for a different one.
      if (workController !== controller) {
        return;
      }
      // Append the new chunks to the existing range. Other fields
      // (work_id, author, work, lang, total, etc.) stay as-is —
      // total is fixed by the work, offset stays at 0 for the
      // first-page anchor, limit stays as the FIRST-page limit
      // for backward-compat with callers that read it. The actual
      // window extent is now derivable as ``chunks.length``.
      setRange({
        ...cur,
        chunks: [...cur.chunks, ...next.chunks],
      });
      // Extend companion maps for the newly-revealed window.
      _fetchCompanionMaps(
        cur.work_id,
        cur.lang,
        next.offset,
        next.chunks.length,
        controller,
      );
    } catch (err) {
      if (isAbortError(err)) return;
      // Silent on pagination errors — the user can scroll to retry.
      // A persistent failure surfaces as no new content appearing,
      // which is visible without an error toast cluttering the UI.
    } finally {
      setLoadingMore(false);
    }
  }

  // Single load path: this effect runs on mount AND whenever workId /
  // focusChunkId change, so the previous `onMount(loadWork)` +
  // separate effect produced two requests on first paint. The effect
  // alone is sufficient — Solid runs it synchronously after the
  // initial render.
  createEffect(() => {
    // Bare property accesses register Solid signal reads so the
    // effect re-runs when either changes. They look like dead code
    // to ESLint; the void-comma form keeps it quiet without altering
    // semantics.
    void (props.workId, props.focusChunkId);
    void loadWork();
  });

  // Cancel any in-flight load when the component tears down so a
  // stale response can't apply state after unmount.
  onCleanup(() => {
    workController?.abort();
  });

  return { range, occMap, refsMap, loadError, loadMore, hasMore, loadingMore };
}
