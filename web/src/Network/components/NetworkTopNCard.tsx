// Reusable Top-N card shell for the mobile Network surface.
//
//   ┌─ <title> ─────────────── <meta> ─┐
//   │ row 1 (caller-supplied)          │
//   │ row 2                            │
//   │ …                                │
//   │ Show all N → (when total > limit)│
//   └──────────────────────────────────┘
//
// Used by `MobileTopPairsCard` (author→author citation pairs) and
// `MobileMostCitedCard` (works leaderboard). Both differ only in
// row content + the labels they show; the head, slicing, and
// "Show all N →" affordance live here so the per-card files stay
// focused on row rendering.

import { For, Show } from "solid-js";
import type { JSX } from "@solidjs/web";

interface Props<T> {
  /** Italic-serif title shown on the left of the card head (e.g.
   *  "Top author pairs", "Most-cited works"). */
  title: string;
  /** Mono-caps meta string shown on the right of the head (e.g.
   *  "10 of 1,156", "leaderboard"). */
  meta: string;
  /** Full dataset; the card slices to the first `limit` for display. */
  items: T[];
  /** How many rows to render in the at-a-glance view. */
  limit: number;
  /** Renders one row. Index is 0-based; the row markup is responsible
   *  for any rank display. */
  renderRow: (item: T, index: number) => JSX.Element;
  /** Tag attribute for mobile.css to hook into for per-card spacing
   *  overrides (matches existing `data-panel` convention used by the
   *  desktop net-panel grid). */
  dataPanel: string;
  /** Tapped when the user wants the full list. Optional — when
   *  omitted, the "Show all N →" affordance is hidden. */
  onShowAll?: () => void;
}

export function NetworkTopNCard<T>(props: Props<T>) {
  const visible = () => props.items.slice(0, props.limit);
  const total = () => props.items.length;
  // "Show all 10 →" is design-canonical even when the dataset has
  // fewer than 10 rows (it indicates the full set). Use `min(10, N)`
  // to avoid claiming more rows than exist.
  const showAllLabel = () => `Show all ${Math.min(10, total())} →`;

  return (
    <section class="net-panel" data-panel={props.dataPanel}>
      <div class="nw-card-head">
        <span class="nw-card-title">{props.title}</span>
        <span class="nw-card-meta">{props.meta}</span>
      </div>
      <For each={visible()}>
        {/* The fragment keeps the call tracked: a row whose position
            changes (or a swapped renderRow) re-renders with the new
            index instead of keeping the one it was first built with. */}
        {(item, i) => <>{props.renderRow(item, i())}</>}
      </For>
      <Show when={props.onShowAll && total() > props.limit}>
        <button type="button" class="nw-more" onClick={() => props.onShowAll?.()}>
          {showAllLabel()}
        </button>
      </Show>
    </section>
  );
}
