// Curator review surface for `curator_status='auto'` cross-references.

import { Show, createEffect, createMemo, createSignal, onCleanup, onMount } from "solid-js";
import {
  fetchReferencesSources,
  fetchReviewQueue,
  updateReferenceCuration,
  type ReviewQueueRow,
} from "~/api/refsApi";
import { LoadingDots } from "~/components/LoadingDots";
import { FilterSheet } from "~/components/FilterSheet";
import { useMobileShell } from "~/components/MobileShellContext";
import { useAbortableFetch } from "~/hooks/useAbortableFetch";
import { usePaginatedAppend } from "~/hooks/usePaginatedAppend";
import { errorMessage } from "~/utils/util";
import { ReviewCard } from "~/Refs/components/ReviewCard";
import { RefsFiltersBar } from "~/Refs/components/RefsFiltersBar";
import { RefsPageHeader } from "~/Refs/components/RefsPageHeader";
import { REFS_PAGE_SIZE, mergeRefsNavigate, useRefsSourceAuthors } from "~/Refs/components/refsList";
import "~/Refs/refs.css";
import "~/Refs/review.css";

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
    offset: number;
  }>({ total_pending: 0, offset: 0 });
  const [cursor, setCursor] = createSignal(0);
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
    setMeta({ total_pending: res.total_pending, offset: 0 });
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
    const landed = rows[idx >= 0 ? idx : 0];
    if (landed && landed.id !== targetId) {
      props.onNavigateToReference(landed.id);
    } else if (!landed && targetId !== undefined) {
      // Empty queue with a stale id in the URL — clear it.
      props.onNavigateToReference(undefined);
    }
  });

  const currentRow = createMemo<ReviewQueueRow | null>(() => {
    const q = queue();
    const c = cursor();
    return c < q.length ? q[c] : null;
  });

  createEffect(() => {
    const row = currentRow();
    setNoteDraft(row?.note ?? "");
  });

  const advanceAfterWrite = async (): Promise<void> => {
    const nextCursor = cursor() + 1;
    setCursor(nextCursor);
    const localCount = queue().length;
    const m = meta();
    if (nextCursor >= localCount && m.offset + localCount < m.total_pending) {
      await pagination.loadMore(firstPage(), async (offset) => {
        const res = await fetchReviewQueue({
          limit: PAGE_SIZE,
          offset,
          sourceAuthor: props.sourceAuthor,
          referenceType: props.referenceType,
        });
        setMeta({
          total_pending: res.total_pending,
          offset: m.offset,
        });
        return { items: res.references };
      });
      if (pagination.appendError()) {
        setActionError(pagination.appendError());
      }
    }
    // Sync the URL to the new current row's id. `replaceState` keeps
    // the back button from accumulating a history entry per review
    // action — see RoutingApi.replace in routing.ts.
    const nextRow = queue()[nextCursor];
    props.onNavigateToReference(nextRow?.id);
  };

  const submit = async (status: "approved" | "rejected"): Promise<void> => {
    const row = currentRow();
    if (!row || acting()) return;
    setActing(true);
    try {
      const note = noteDraft().trim();
      await updateReferenceCuration(row.id, {
        curator_status: status,
        curator_note: note ? note : null,
      });
      setMeta({
        ...meta(),
        total_pending: Math.max(0, meta().total_pending - 1),
      });
      await advanceAfterWrite();
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setActing(false);
    }
  };

  const skip = (): void => {
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
    const c = cursor();
    if (c <= 0) return;
    setCursor(c - 1);
    setNoteDraft(queue()[c - 1]?.note ?? "");
    props.onNavigateToReference(queue()[c - 1]?.id);
  };
  const goNext = (): void => {
    // Same forward path as the Skip button — no curator status change,
    // just advance + URL update.
    void advanceAfterWrite();
  };

  onMount(() => {
    const onKey = (e: KeyboardEvent): void => {
      // Don't hijack keys while the curator is typing the note. Match
      // form-element tags loosely so future widgets (selects, etc.)
      // also let their own keystrokes through.
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === "textarea" || tag === "input" || tag === "select") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "ArrowDown" || e.key === "ArrowRight" || e.key === "j") {
        e.preventDefault();
        goNext();
      } else if (e.key === "ArrowUp" || e.key === "ArrowLeft" || e.key === "k") {
        e.preventDefault();
        goPrev();
      }
    };
    window.addEventListener("keydown", onKey);
    onCleanup(() => window.removeEventListener("keydown", onKey));
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
      pageEl?.removeEventListener("wheel", onWheel);
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
