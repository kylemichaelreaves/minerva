// Curator review surface for `curator_status='auto'` cross-references.

import {
  Show,
  createEffect,
  createMemo,
  createSignal,
  onCleanup,
  onMount,
  untrack,
} from "solid-js";
import {
  fetchReferencesSources,
  fetchReviewQueue,
  updateReferenceCuration,
  type ReviewQueueRow,
} from "~/api/refsApi";
import { LoadingDots } from "~/components/primitives/LoadingDots";
import { FilterSheet } from "~/components/shell/FilterSheet";
import { useMobileShell } from "~/components/shell/MobileShellContext";
import { useAbortableFetch } from "~/hooks/useAbortableFetch";
import { useListKeyboardNav } from "~/hooks/useListKeyboardNav";
import { usePaginatedAppend } from "~/hooks/usePaginatedAppend";
import { errorMessage } from "~/utils/util";
import { ReviewCard } from "~/features/Refs/components/ReviewCard";
import { RefsFiltersBar } from "~/features/Refs/components/RefsFiltersBar";
import { RefsPageHeader } from "~/features/Refs/components/RefsPageHeader";
import {
  REFS_PAGE_SIZE,
  mergeRefsNavigate,
  useRefsSourceAuthors,
} from "~/features/Refs/components/refsList";
import "~/features/Refs/refs.css";
import "~/features/Refs/review.css";

export interface ReviewProps {
  sourceAuthor?: string;
  referenceType?: string;
  /** Reference id from the URL. Resolves to a queue cursor on load
   *  so the page is bookmarkable / refresh-stable; without this the
   *  local cursor reset to 0 on every reload, losing the curator's
   *  place. */
  referenceId?: number;
  onNavigate: (filters: { sourceAuthor?: string; referenceType?: string }) => void;
  /** Update the URL's `?id=<n>` in place via history.replaceState as
   *  the cursor advances. Distinct from `onNavigate` (which is a real
   *  filter-change pushState) so per-item advance doesn't bloat the
   *  back-button stack. `undefined` clears the id (end of queue). */
  onNavigateToReference: (referenceId: number | undefined) => void;
  onOpenSource: (workTitle: string, chunkId: string) => void;
}

const PAGE_SIZE = REFS_PAGE_SIZE;

export default function Review(props: ReviewProps) {
  const shell = useMobileShell();

  onMount(() => {
    shell.registerSurfaceActions({
      openFilters: () => shell.setFiltersSheetOpen(true),
    });
  });

  const [meta, setMeta] = createSignal<{
    total_pending: number;
  }>({ total_pending: 0 });
  const [cursor, setCursor] = createSignal(0);
  // Approve/reject decisions remove rows from the SERVER-side pending
  // queue, so the next unseen row sits at server offset
  // `localCount - decidedCount`, not `localCount`. Skips don't count —
  // skipped rows stay pending and keep their queue position.
  const [decidedCount, setDecidedCount] = createSignal(0);
  const [noteDraft, setNoteDraft] = createSignal<string>("");
  const [acting, setActing] = createSignal(false);

  const {
    data,
    loading,
    error: fetchError,
  } = useAbortableFetch(
    () => ({
      limit: PAGE_SIZE,
      offset: 0,
      sourceAuthor: props.sourceAuthor,
      referenceType: props.referenceType,
    }),
    fetchReviewQueue,
  );

  const pagination = usePaginatedAppend<ReviewQueueRow>(() => data());
  const firstPage = (): ReviewQueueRow[] => data()?.references ?? [];
  const queue = (): ReviewQueueRow[] => pagination.rows(firstPage());

  const { data: sourcesData } = useAbortableFetch(() => ({}), fetchReferencesSources);
  const sourceAuthors = useRefsSourceAuthors(sourcesData, () => data()?.references);

  const [actionError, setActionError] = createSignal<string | null>(null);
  const error = () => fetchError() ?? actionError();

  createEffect(() => {
    const res = data();
    if (res === null) return;
    // Everything below is keyed ONLY on a fresh queue fetch. In
    // particular `props.referenceId` must be read untracked: this
    // effect WRITES the URL id (onNavigateToReference), so tracking
    // the prop made the effect re-trigger itself and fight the
    // cursor-advance path for ownership of the cursor.
    untrack(() => {
      setMeta({ total_pending: res.total_pending });
      setDecidedCount(0);
      // Resolve the URL's referenceId (if any) to a cursor position
      // within the freshly-loaded queue. Falls back to cursor 0 when
      // the id isn't in the queue (already approved, behind the
      // current filter, etc.) — common enough on a stale bookmark.
      const targetId = props.referenceId;
      const rows = res.references;
      const idx = targetId === undefined ? 0 : rows.findIndex((r) => r.id === targetId);
      setCursor(idx >= 0 ? idx : 0);
      setNoteDraft("");
      // If the URL had no id, or the id wasn't found, sync the URL to
      // the row we actually landed on so the link is shareable.
      const landed = rows.at(idx >= 0 ? idx : 0);
      if (landed && landed.id !== targetId) {
        props.onNavigateToReference(landed.id);
      } else if (!landed && targetId !== undefined) {
        // Empty queue with a stale id in the URL — clear it.
        props.onNavigateToReference(undefined);
      }
    });
  });

  const currentRow = createMemo<ReviewQueueRow | null>(() => {
    const q = queue();
    const c = cursor();
    return q[c] ?? null;
  });

  createEffect(() => {
    const row = currentRow();
    setNoteDraft(row?.note ?? "");
  });

  const advanceAfterWrite = async (): Promise<void> => {
    const c = cursor();
    const q = queue();
    const localCount = q.length;
    if (localCount === 0) return;

    const m = meta();
    const decided = decidedCount();
    const hasMoreOnServer = localCount - decided < m.total_pending;

    if (c < localCount - 1) {
      const nextCursor = c + 1;
      setCursor(nextCursor);
      setActionError(null);
      props.onNavigateToReference(q[nextCursor]?.id);
      return;
    }

    if (!hasMoreOnServer) return;

    // The page fetcher runs once, inside this event-driven call, and must read
    // the filters current at that moment; there is nothing to track.
    // eslint-disable-next-line solid/reactivity -- one-shot fetch callback, reads props at call time by design
    await pagination.loadMore(firstPage(), async (offset, signal) => {
      const res = await fetchReviewQueue(
        {
          limit: PAGE_SIZE,
          offset: offset - decided,
          sourceAuthor: props.sourceAuthor,
          referenceType: props.referenceType,
        },
        signal,
      );
      setMeta({ total_pending: res.total_pending });
      return { items: res.references };
    });
    if (pagination.appendError()) {
      setActionError(pagination.appendError());
      return;
    }

    const grown = queue();
    if (grown.length <= localCount) return;

    const nextCursor = c + 1;
    setCursor(nextCursor);
    setActionError(null);
    props.onNavigateToReference(grown[nextCursor]?.id);
  };

  const submit = async (status: "approved" | "rejected"): Promise<void> => {
    const row = currentRow();
    if (!row || acting()) return;
    setActing(true);
    setActionError(null);
    try {
      const note = noteDraft().trim();
      await updateReferenceCuration(row.id, {
        curator_status: status,
        curator_note: note ? note : null,
      });
      setMeta({
        total_pending: Math.max(0, meta().total_pending - 1),
      });
      setDecidedCount((c) => c + 1);
      await advanceAfterWrite();
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setActing(false);
    }
  };

  const skip = (): void => {
    if (acting()) return;
    void advanceAfterWrite();
  };

  // ── Keyboard + wheel navigation ──────────────────────────────────
  // Arrow keys / j-k navigate forward and backward through the queue
  // without committing a curator decision (matches the `Skip` button's
  // semantics). Mouse-wheel does the same with an accumulated-delta
  // threshold so a single scroll-tick equals one navigation, and the
  // handler falls through to native scroll when the user is inside the
  // source-text blockquote (which has its own overflow-y:auto).
  const goPrev = (): void => {
    if (acting()) return;
    const c = cursor();
    if (c <= 0) return;
    setCursor(c - 1);
    setNoteDraft(queue()[c - 1]?.note ?? "");
    props.onNavigateToReference(queue()[c - 1]?.id);
  };
  const goNext = (): void => {
    if (acting()) return;
    // Same forward path as the Skip button — no curator status change,
    // just advance + URL update.
    void advanceAfterWrite();
  };

  // Shared list-nav hook — owns the form-element guard (input,
  // textarea, select, contenteditable) and the listener lifecycle.
  // Muted while the mobile filter sheet is open so its controls keep
  // their keys.
  useListKeyboardNav({
    enabled: () => !shell.filtersSheetOpen(),
    horizontal: true,
    onNext: goNext,
    onPrev: goPrev,
  });

  // Wheel handler — attached at the .review-page root via ref below.
  // `wheelAccum` collects deltaY between firings so a noisy trackpad
  // doesn't jump past several references. Resets after a cooldown so a
  // pause between flicks doesn't carry forward.
  let pageEl: HTMLDivElement | undefined;
  let wheelAccum = 0;
  let wheelLast = 0;
  const WHEEL_THRESHOLD = 80;
  const WHEEL_COOLDOWN_MS = 300;
  const onWheel = (e: WheelEvent): void => {
    if (acting()) return;
    // Walk up from the wheel target — if it sits inside a scrollable
    // element that still has room to scroll IN THE WHEEL DIRECTION,
    // yield to native scrolling. Otherwise we eat the wheel and use it
    // for navigation. This means scrolling inside the source-text
    // blockquote works as expected, and only spills over to
    // next/previous when you hit the top/bottom of that text.
    let el: HTMLElement | null = e.target as HTMLElement | null;
    while (el && el !== pageEl) {
      const style = getComputedStyle(el);
      const ovy = style.overflowY;
      const scrollable = (ovy === "auto" || ovy === "scroll") && el.scrollHeight > el.clientHeight;
      if (scrollable) {
        const atTop = el.scrollTop <= 0;
        const atBot = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
        if ((e.deltaY < 0 && !atTop) || (e.deltaY > 0 && !atBot)) return;
        break;
      }
      el = el.parentElement;
    }
    e.preventDefault();
    const now = performance.now();
    if (now - wheelLast > WHEEL_COOLDOWN_MS) wheelAccum = 0;
    wheelAccum += e.deltaY;
    wheelLast = now;
    if (wheelAccum >= WHEEL_THRESHOLD) {
      wheelAccum = 0;
      goNext();
    } else if (wheelAccum <= -WHEEL_THRESHOLD) {
      wheelAccum = 0;
      goPrev();
    }
  };
  onMount(() => {
    if (!pageEl) return;
    // passive: false so preventDefault() works.
    pageEl.addEventListener("wheel", onWheel, { passive: false });
    onCleanup(() => {
      pageEl.removeEventListener("wheel", onWheel);
    });
  });

  const filtersBar = () => (
    <RefsFiltersBar
      variant="review"
      sourceAuthor={props.sourceAuthor}
      referenceType={props.referenceType}
      sourceOptions={sourceAuthors()}
      onChange={(patch) => {
        props.onNavigate(
          mergeRefsNavigate(
            {
              sourceAuthor: props.sourceAuthor,
              referenceType: props.referenceType,
            },
            patch,
          ),
        );
      }}
    />
  );

  return (
    <div class="refs-page review-page" ref={pageEl}>
      <RefsPageHeader
        title="Curator review"
        loading={loading()}
        error={error()}
        meta={
          <>
            <p class="review-sub">
              Triage <code>curator_status='auto'</code> rows. Lowest- confidence first.
            </p>
            <Show when={!loading()}>
              <span class="refs-meta">{Math.max(0, meta().total_pending)} pending</span>
            </Show>
          </>
        }
      />

      <FilterSheet>{filtersBar()}</FilterSheet>

      <Show
        when={!loading() && currentRow()}
        fallback={
          <Show
            when={loading()}
            fallback={
              <div class="review-empty">
                <p>No more rows pending under these filters.</p>
              </div>
            }
          >
            <p class="refs-meta">
              loading
              <LoadingDots />
            </p>
          </Show>
        }
      >
        {(rowAccessor) => (
          <ReviewCard
            row={rowAccessor()}
            noteDraft={noteDraft()}
            onNoteChange={setNoteDraft}
            disabled={acting()}
            onApprove={() => void submit("approved")}
            onReject={() => void submit("rejected")}
            onSkip={skip}
            onOpenSource={(work, chunk) => {
              props.onOpenSource(work, chunk);
            }}
          />
        )}
      </Show>
    </div>
  );
}
