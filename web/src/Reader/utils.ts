// Pure helpers for the Reader. Kept in a sibling file so the
// JSX-bearing component files don't drown in non-render logic.

import type { TermOccurrenceSpan } from "~/utils/types";

/** Find the term occurrence whose [start, end) range covers a given
 *  word's offset. Linear scan — occurrences-per-chunk is small
 *  (single digits in practice). Returns null when the word is not
 *  part of any term occurrence. */
export function occurrenceFor(
  occs: TermOccurrenceSpan[],
  offset: number,
  length: number,
): TermOccurrenceSpan | null {
  for (const o of occs) {
    if (o.source_start <= offset && offset + length <= o.source_end) {
      return o;
    }
  }
  return null;
}

/** Derive a citation ref string from the current selection's
 *  surrounding `[data-chunk-id]` line elements. Falls back to
 *  "Selection" if the selection spans multiple chunks or none can
 *  be determined. Used by the `onMouseUp` translate flow. */
export function inferRefFromSelection(sel: Selection): string {
  if (sel.rangeCount === 0) return "Selection";
  const range = sel.getRangeAt(0);
  let node: Node | null = range.startContainer;
  while (node && node.nodeType !== Node.ELEMENT_NODE) node = node.parentNode;
  const startLine = (node as Element | null)?.closest(".line") as HTMLElement | null;
  let endNode: Node | null = range.endContainer;
  while (endNode && endNode.nodeType !== Node.ELEMENT_NODE) endNode = endNode.parentNode;
  const endLine = (endNode as Element | null)?.closest(".line") as HTMLElement | null;
  if (!startLine) return "Selection";
  const startSec = startLine.querySelector(".num")?.textContent ?? "?";
  if (endLine && endLine !== startLine) {
    const endSec = endLine.querySelector(".num")?.textContent ?? "?";
    return `${startSec.trim()} — ${endSec.trim()}`;
  }
  return startSec.trim();
}

/** One contiguous highlight inside a single chunk. Cross-chunk
 *  selections become multiple of these. `start` / `end` are
 *  character offsets into the chunk text, matching the convention
 *  used by `LemmaHighlights` and `TermOccurrenceSpan`. */
export interface PinnedHighlight {
  chunkId: string;
  start: number;
  end: number;
  /** True after the user dismisses the rail — switches the visual
   *  to the hairline underline marker. */
  saved: boolean;
}

/** Walk every `.gw` word element inside a `.line` and decide which
 *  offsets the Range covers. The Range is the source of truth for
 *  *which words* the user selected — we don't try to interpret
 *  partial-word ranges; selecting half of "ἀγαθοῦ" pins the whole
 *  word. */
function wordOffsetsCoveredByRange(
  line: HTMLElement,
  range: Range,
): { min: number; max: number } | null {
  let min = Number.POSITIVE_INFINITY;
  let max = -1;
  const words = line.querySelectorAll<HTMLElement>(".gw, .term-mark");
  for (const w of words) {
    if (!range.intersectsNode(w)) continue;
    const offAttr = w.getAttribute("data-offset");
    if (offAttr == null) continue;
    const off = Number.parseInt(offAttr, 10);
    if (Number.isNaN(off)) continue;
    const len = w.textContent.length;
    if (off < min) min = off;
    if (off + len > max) max = off + len;
  }
  return max >= 0 ? { min, max } : null;
}

/** Convert a Selection into one or more PinnedHighlight rows — one
 *  per chunk the selection touches. Cross-chunk selections naturally
 *  produce multiple highlights with the same `saved` flag. */
export function pinnedHighlightsFromSelection(
  sel: Selection,
  stage: HTMLElement | undefined,
): PinnedHighlight[] {
  if (!stage || sel.rangeCount === 0 || sel.isCollapsed) return [];
  const range = sel.getRangeAt(0);
  const lines = stage.querySelectorAll<HTMLElement>(".line[data-chunk-id]");
  const out: PinnedHighlight[] = [];
  for (const line of lines) {
    if (!range.intersectsNode(line)) continue;
    const chunkId = line.getAttribute("data-chunk-id");
    if (!chunkId) continue;
    const range2 = document.createRange();
    range2.selectNodeContents(line);
    // Narrow the range to the line's intersection with the user's
    // selection. cloneRange'd then surgically nudged: anything
    // outside the line is irrelevant for word-coverage.
    if (
      range.startContainer === line ||
      line.contains(range.startContainer)
    ) {
      try {
        range2.setStart(range.startContainer, range.startOffset);
      } catch {
        /* leave at line start */
      }
    }
    if (range.endContainer === line || line.contains(range.endContainer)) {
      try {
        range2.setEnd(range.endContainer, range.endOffset);
      } catch {
        /* leave at line end */
      }
    }
    const cov = wordOffsetsCoveredByRange(line, range2);
    if (!cov) continue;
    out.push({ chunkId, start: cov.min, end: cov.max, saved: false });
  }
  return out;
}

/** Selection size summary used in the toolbar (e.g. "4 words · 22 chars"). */
export function selectionSummary(text: string): { count: string; words: number } {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  const chars = text.length;
  if (words <= 1) return { count: `${words} word`, words };
  return { count: `${words} words · ${chars} chars`, words };
}

/** Whether the dependency-syntax action applies to what's on screen.
 *
 *  Prefers `rangeLang` — the language the server actually resolved for the
 *  loaded range (`WorkRange.lang`) — over `sourceLang`, the route/prop hint.
 *  `sourceLang` is `undefined` on citation deep-links (`App.tsx`'s
 *  `openAtChunk` passes it as `undefined`) and on the syntax route's own
 *  return trip, so gating on it alone leaves German text with no Syntax
 *  action at all in those paths. Falling back to it keeps the gate lit
 *  before the range has loaded (first paint, `rangeLang` is `undefined`)
 *  when the caller *does* have a lang hint.
 *
 *  The parser is German-only (`syntax/parse.py:_LANG = "de"`); the server
 *  refuses non-German independently (400) — this is convenience, not the
 *  safety property. */
export function isSyntaxLangEnabled(
  rangeLang: string | undefined,
  sourceLang: string | undefined,
): boolean {
  return (rangeLang ?? sourceLang) === "deu";
}

/** Which transient Reader surfaces are open. Every one of them already
 *  answers Escape itself. */
export interface ReaderSurfaces {
  /** Translate rail (`useTranslateRail`), open on any non-idle kind. */
  rail: boolean;
  /** Term-card popover (`useTermCard`), also resumable from `?term=`. */
  termCard: boolean;
  /** Cross-reference card (`useXrefCard`). */
  xrefCard: boolean;
  /** Selection toolbar (`useSelectionToolbar`). */
  selectionToolbar: boolean;
  /** Mobile reader-settings sheet (`MobileShellContext`). */
  settingsSheet: boolean;
  /** Dependency-syntax overlay, open as `?syntax=<chunk>` on the reader
   *  route. It is a LAYER over a Reader that stays mounted (#342), so
   *  the Reader's own Escape listener is live while the overlay owns
   *  the key — it was not before, because the Reader was unmounted. */
  syntaxLayer: boolean;
}

/**
 * Whether Escape should leave the Reader for the landing.
 *
 * Only when nothing else is using the key. Escape is what dismisses each
 * surface above, so an ungated exit would take the whole reader away with the
 * card the user meant to close — and a surface that owns Escape must win it,
 * which is what makes the second press the one that leaves.
 *
 * A seventh surface added to the Reader joins `ReaderSurfaces`, and the
 * wiring in `Reader/index.tsx` supplies it. The type is what makes that a
 * compile error rather than a silent hole.
 */
export function escapeExitsReader(open: ReaderSurfaces): boolean {
  return !Object.values(open).some(Boolean);
}
