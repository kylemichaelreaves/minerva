// Selection toolbar + pinned highlights state machine.
//
// Drag-to-select on the reader surface settles into a floating action
// toolbar; the actual /api/translate call only fires when the user
// commits via Translate (or T). Committing converts the native
// selection into app-painted PinnedHighlight spans that survive the
// browser clearing the selection; dismissing the rail flips them to
// "saved" underline markers that re-open the cached translation when
// clicked.
//
// The hook owns the toolbar signal, the pinned highlight set, the
// saved-translation map (so saved-marker clicks can re-issue
// /api/translate without reconstructing the selection from the DOM),
// and the keyboard / outside-click effect that gates dismissal.

import { createEffect, createSignal, onCleanup, type Accessor } from "solid-js";
import { useClickOutside } from "~/hooks/useClickOutside";
import {
  loadHighlights,
  saveHighlights,
  type SavedHighlight,
} from "~/utils/highlightStorage";
import {
  inferRefFromSelection,
  pinnedHighlightsFromSelection,
  selectionSummary,
  type PinnedHighlight,
} from "~/Reader/utils";

export interface SelToolbar {
  rect: DOMRect;
  text: string;
  ref: string;
  pinned: PinnedHighlight[];
  summary: string;
  singleWord: boolean;
}

export interface SelectionToolbarApi {
  selToolbar: () => SelToolbar | null;
  pinnedHighlights: () => PinnedHighlight[];
  onMouseUp: (e: MouseEvent) => void;
  commitTranslate: (t: SelToolbar) => void;
  commitLookup: (t: SelToolbar) => void;
  copySelection: (t: SelToolbar) => void;
  onPinnedClick: (chunkId: string, start: number, end: number) => void;
  /** Convert any active pinned highlight to a saved underline marker.
   *  Called from the rail-dismiss path. The underline marker and the
   *  metadata needed to re-open it (source + ref) are persisted to
   *  localStorage via `highlightStorage` so they survive reloads. */
  markAllPinnedSaved: () => void;
  /** Delete a saved highlight by (chunkId, start, end). Used by the
   *  right-click "Remove" affordance on the pin-hl span. */
  removeSavedHighlight: (chunkId: string, start: number, end: number) => void;
  /** Imperatively close the floating toolbar. */
  dismissToolbar: () => void;
}

export interface SelectionToolbarProps {
  getStage: Accessor<HTMLDivElement | undefined>;
  /** Current work id, used to scope persisted highlights. The hook
   *  reloads the saved-marker layer when this changes (new work → new
   *  annotation set). */
  workId: Accessor<string>;
  /** Called by the commit-translate path (T key, click, or
   *  saved-marker re-open). */
  onTranslateRequest: (source: string, ref: string) => void;
  /** Called by the commit-lookup fork (single-word selection + L). */
  onLookupRequest: (
    word: string,
    chunkId: string,
    offset: number,
    lineEl: Element | null,
  ) => void;
}

export function useSelectionToolbar(
  props: SelectionToolbarProps,
): SelectionToolbarApi {
  const [selToolbar, setSelToolbar] = createSignal<SelToolbar | null>(null);
  const [pinnedHighlights, setPinnedHighlights] = createSignal<
    PinnedHighlight[]
  >([]);

  const savedTranslations = new Map<
    string,
    { source: string; ref: string }
  >();
  const savedKey = (chunkId: string, start: number, end: number) =>
    `${chunkId}:${start}:${end}`;

  // ── Persistence ─────────────────────────────────────────────────
  //
  // On every workId change: load the saved-highlight layer from
  // localStorage and seed both `pinnedHighlights` (with saved=true so
  // they render as underline markers) and `savedTranslations` (so a
  // click on a marker can re-fire /api/translate without re-deriving
  // the source from the DOM). Switching works wipes the existing
  // in-memory state — the new work's annotations are scoped to that
  // work's storage key.
  createEffect(() => {
    const workId = props.workId();
    const stored = loadHighlights(workId);
    savedTranslations.clear();
    for (const h of stored) {
      savedTranslations.set(savedKey(h.chunkId, h.start, h.end), {
        source: h.source,
        ref: h.ref,
      });
    }
    setPinnedHighlights(
      stored.map((h) => ({
        chunkId: h.chunkId,
        start: h.start,
        end: h.end,
        saved: true,
      })),
    );
  });

  function persistSavedHighlights(workId: string): void {
    // Snapshot every saved=true highlight + its translation metadata
    // into localStorage. Active (saved=false) highlights are omitted
    // — they belong to an open rail, not the persistent layer.
    const snapshot: SavedHighlight[] = [];
    for (const p of pinnedHighlights()) {
      if (!p.saved) continue;
      const meta = savedTranslations.get(savedKey(p.chunkId, p.start, p.end));
      if (!meta) continue; // missing meta — drop on the floor
      snapshot.push({
        chunkId: p.chunkId,
        start: p.start,
        end: p.end,
        source: meta.source,
        ref: meta.ref,
      });
    }
    saveHighlights(workId, snapshot);
  }

  function onMouseUp(e: MouseEvent) {
    // Word clicks call stopPropagation in Lines; this handler runs
    // only for drag-selections on the stage background.
    const target = e.target as Element | null;
    if (target?.closest(".gw, .term-mark, .pin-hl")) {
      return;
    }
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) {
      setSelToolbar(null);
      return;
    }
    const text = sel.toString().trim();
    if (!text) {
      setSelToolbar(null);
      return;
    }
    const ref = inferRefFromSelection(sel);
    const pinned = pinnedHighlightsFromSelection(sel, props.getStage());
    const { count, words } = selectionSummary(text);
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    setSelToolbar({
      rect,
      text,
      ref,
      pinned,
      summary: count,
      singleWord: words <= 1,
    });
  }

  function commitTranslate(t: SelToolbar) {
    setPinnedHighlights((prev) => {
      // Drop any prior active highlights — only one translation is
      // foregrounded at a time. Preserve saved=true markers so the
      // user accumulates an annotation layer as they read.
      const survivors = prev.filter((p) => p.saved);
      return [...survivors, ...t.pinned.map((p) => ({ ...p, saved: false }))];
    });
    const sel = window.getSelection();
    sel?.removeAllRanges();
    setSelToolbar(null);
    for (const p of t.pinned) {
      savedTranslations.set(savedKey(p.chunkId, p.start, p.end), {
        source: t.text,
        ref: t.ref,
      });
    }
    props.onTranslateRequest(t.text, t.ref);
  }

  function commitLookup(t: SelToolbar) {
    // Single-word fork: route to the supplied word-click handler.
    // We re-derive (chunk_id, offset) from the first pinned span.
    setSelToolbar(null);
    const sel = window.getSelection();
    sel?.removeAllRanges();
    const p = t.pinned[0];
    if (p === undefined) return;
    const line =
      props
        .getStage()
        ?.querySelector(`[data-chunk-id="${CSS.escape(p.chunkId)}"]`) ?? null;
    props.onLookupRequest(t.text, p.chunkId, p.start, line);
  }

  function copySelection(t: SelToolbar) {
    // Clipboard writes are best-effort; swallow rejections so a
    // permissions-denied prompt never breaks the dismiss path.
    void navigator.clipboard.writeText(t.text).catch(() => undefined);
    setSelToolbar(null);
  }

  function onPinnedClick(chunkId: string, start: number, end: number) {
    const key = savedKey(chunkId, start, end);
    const saved = savedTranslations.get(key);
    if (!saved) return;
    setPinnedHighlights((prev) =>
      prev.map((p) =>
        p.chunkId === chunkId && p.start === start && p.end === end
          ? { ...p, saved: false }
          : p.saved
            ? p
            : { ...p, saved: true },
      ),
    );
    props.onTranslateRequest(saved.source, saved.ref);
  }

  function markAllPinnedSaved() {
    setPinnedHighlights((prev) => prev.map((p) => ({ ...p, saved: true })));
    persistSavedHighlights(props.workId());
  }

  function removeSavedHighlight(
    chunkId: string,
    start: number,
    end: number,
  ): void {
    setPinnedHighlights((prev) =>
      prev.filter(
        (p) => !(p.chunkId === chunkId && p.start === start && p.end === end),
      ),
    );
    savedTranslations.delete(savedKey(chunkId, start, end));
    persistSavedHighlights(props.workId());
  }

  function dismissToolbar() {
    setSelToolbar(null);
  }

  // Esc / keyboard shortcuts for the selection toolbar.
  createEffect(() => {
    const t = selToolbar();
    if (!t) return;
    const onKey = (e: KeyboardEvent) => {
      // Don't hijack keys while the user is typing in a form field or
      // an editable region — let those widgets keep their keystrokes.
      // (instanceof, not a cast: e.target can be the Document itself,
      // which has no tagName.)
      const el = e.target instanceof HTMLElement ? e.target : null;
      const tag = el?.tagName.toLowerCase();
      if (tag === "textarea" || tag === "input" || tag === "select") return;
      if (el?.isContentEditable) return;
      if (e.key === "Escape") {
        setSelToolbar(null);
        return;
      }
      if (e.key === "t" || e.key === "T") {
        e.preventDefault();
        commitTranslate(t);
        return;
      }
      if ((e.key === "l" || e.key === "L") && t.singleWord) {
        e.preventDefault();
        commitLookup(t);
      }
    };
    document.addEventListener("keydown", onKey);
    // Solid ignores values returned from createEffect — a returned
    // cleanup function would never run, leaking one document-level
    // listener (with a stale toolbar closure) per toolbar open.
    // onCleanup registered inside the effect runs before each re-run
    // and on dispose, which is the behavior we want.
    onCleanup(() => {
      document.removeEventListener("keydown", onKey);
    });
  });

  useClickOutside(
    () =>
      document.querySelector(".selection-toolbar") as HTMLElement | undefined,
    () => selToolbar() !== null,
    () => setSelToolbar(null),
    { event: "mousedown", capture: true },
  );

  return {
    selToolbar,
    pinnedHighlights,
    onMouseUp,
    commitTranslate,
    commitLookup,
    copySelection,
    onPinnedClick,
    markAllPinnedSaved,
    removeSavedHighlight,
    dismissToolbar,
  };
}
