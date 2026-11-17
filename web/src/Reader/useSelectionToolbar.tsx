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
  /** Open the dependency-syntax overlay for the selection's chunk.
   *  No-op when the selection has no pinned span. */
  commitSyntax: (t: SelToolbar) => void;
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
  /** Whether the syntax overlay applies to what is on screen. The parser is
   *  German-only, so the Reader passes `() => sourceLang === "deu"`. Gates
   *  the `S` key; the button is gated by the caller withholding `onSyntax`.
   *  The server refuses non-German independently — this is convenience, not
   *  the guarantee. */
  syntaxEnabled?: () => boolean;
  /** Navigate to the syntax overlay for `chunkId`. */
  onSyntaxRequest?: (chunkId: string) => void;
  /** True while the Reader is retained off-screen behind a step-out route
   *  (#348). The toolbar's hotkeys are bound to `document`, which `inert` on
   *  the Reader does not reach — so T / L / S / Esc would still fire against
   *  a toolbar the user cannot see, on a page that is not the Reader. */
  suspended?: () => boolean;
}

export type ToolbarKeyAction = "dismiss" | "translate" | "lookup" | "syntax";

/** Which toolbar action a keydown should trigger, or null for none.
 *
 *  Pure, and exported, because the listener that consumes it lives in a
 *  `createEffect` gated on an open toolbar — which requires a real DOM
 *  Range to produce. Keeping the decision separate from the dispatch is
 *  what makes the key map testable at all; it was untested before. */
export function toolbarKeyAction(
  e: KeyboardEvent,
  opts: { singleWord: boolean; syntaxEnabled: boolean },
): ToolbarKeyAction | null {
  // Don't hijack keys while the user is typing in a form field or an
  // editable region — let those widgets keep their keystrokes.
  // (instanceof, not a cast: e.target can be the Document itself, which
  // has no tagName.)
  const el = e.target instanceof HTMLElement ? e.target : null;
  const tag = el?.tagName.toLowerCase();
  if (tag === "textarea" || tag === "input" || tag === "select") return null;
  if (el?.isContentEditable) return null;

  if (e.key === "Escape") return "dismiss";
  if (e.key === "t" || e.key === "T") return "translate";
  if ((e.key === "l" || e.key === "L") && opts.singleWord) return "lookup";
  if ((e.key === "s" || e.key === "S") && opts.syntaxEnabled) return "syntax";
  return null;
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

  function onMouseUp(_e: MouseEvent) {
    // Deliberately does NOT test which element the pointer landed on.
    //
    // This used to return early when `e.target.closest(".gw, .term-mark,
    // .pin-hl")` matched, on the stated grounds that "word clicks call
    // stopPropagation in Lines". That premise is false: `WordRun` stops
    // propagation from an `onClick` handler, and `click` is not `mouseup` —
    // nothing ever stopped the mouseup, so it always reached here.
    //
    // Every word is wrapped in `<span class="gw">`, and a drag ends with
    // the pointer on a word, so the guard suppressed the toolbar for the
    // ordinary case. Measured in Chrome on one selection, varying only the
    // release target: over a word (.gw) -> no toolbar; between words
    // (.text) -> toolbar; on the line (.line) -> toolbar.
    //
    // The question it reached for is click-vs-drag, and the collapse check
    // below already answers it: a click collapses the selection, a drag
    // does not. See #591.
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

  /** Close the toolbar and drop the browser selection. Every commit path
   *  does this before handing off; the two operations are independent and
   *  synchronous, so the order the call sites used to differ in never
   *  mattered. */
  function closeSelection() {
    setSelToolbar(null);
    window.getSelection()?.removeAllRanges();
  }

  function commitTranslate(t: SelToolbar) {
    setPinnedHighlights((prev) => {
      // Drop any prior active highlights — only one translation is
      // foregrounded at a time. Preserve saved=true markers so the
      // user accumulates an annotation layer as they read.
      const survivors = prev.filter((p) => p.saved);
      return [...survivors, ...t.pinned.map((p) => ({ ...p, saved: false }))];
    });
    closeSelection();
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
    closeSelection();
    const p = t.pinned[0];
    if (p === undefined) return;
    const line =
      props
        .getStage()
        ?.querySelector(`[data-chunk-id="${CSS.escape(p.chunkId)}"]`) ?? null;
    props.onLookupRequest(t.text, p.chunkId, p.start, line);
  }

  function commitSyntax(t: SelToolbar) {
    // The chunk comes off the first pinned span — the one the selection
    // started in — same derivation as commitLookup.
    closeSelection();
    const p = t.pinned[0];
    if (p === undefined) return;
    props.onSyntaxRequest?.(p.chunkId);
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
    // Deliberate per-run snapshot: the effect re-runs on every toolbar change and onCleanup drops the listener holding the old `t`.
    const t = selToolbar();
    if (!t) return;
    if (props.suspended?.()) return;
    const onKey = (e: KeyboardEvent) => {
      const action = toolbarKeyAction(e, {
        singleWord: t.singleWord,
        syntaxEnabled: props.syntaxEnabled?.() ?? false,
      });
      if (action === null) return;
      if (action === "dismiss") {
        setSelToolbar(null);
        return;
      }
      e.preventDefault();
      if (action === "translate") commitTranslate(t);
      else if (action === "lookup") commitLookup(t);
      else commitSyntax(t);
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
    commitSyntax,
    copySelection,
    onPinnedClick,
    markAllPinnedSaved,
    removeSavedHighlight,
    dismissToolbar,
  };
}
