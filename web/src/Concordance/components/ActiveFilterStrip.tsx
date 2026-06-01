// Active-filter chip strip with per-chip remove and a global reset.
// Used above the leaderboard on F1 and inside the applied-filters card
// on F2's unified rail. Each chip is a `{ k, v, onRemove }` triple; the
// strip shows a live result count when one is passed.

import { For, Show } from "solid-js";

export interface ActiveChip {
  /** Short label shown in the chip's kicker (e.g. ``POS``, ``case``). */
  k: string;
  /** The active value (e.g. ``noun``, ``Nom``). */
  v: string;
  onRemove: () => void;
}

export function ActiveFilterStrip(props: {
  items: ActiveChip[];
  /** Total result count after filtering — surfaced so users can see
   *  the cost of narrowing/broadening at a glance. */
  count?: number;
  countLabel?: string;
  onReset: () => void;
}) {
  return (
    <Show when={props.items.length > 0}>
      <div class="afs">
        <span class="afs-lab">
          Active · {props.items.length}
        </span>
        <For each={props.items}>
          {(it) => (
            <span class="afs-pill">
              <span class="k">{it.k}</span>
              <span>{it.v}</span>
              <span class="x" onClick={(e) => { e.stopPropagation(); it.onRemove(); }}>
                ×
              </span>
            </span>
          )}
        </For>
        <Show when={props.count !== undefined}>
          <span class="afs-ct">
            <b>{props.count!.toLocaleString()}</b> {props.countLabel ?? "results"}
          </span>
        </Show>
        <span class="afs-reset" onClick={() => props.onReset()}>
          ↺ reset all
        </span>
      </div>
    </Show>
  );
}
