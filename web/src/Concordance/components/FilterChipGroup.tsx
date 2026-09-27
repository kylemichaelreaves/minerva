// A labelled group of toggle chips for the F2 filter rail. The Case,
// Number and Surface sections were three copies of the same markup —
// a label with an optional applied-badge + clear link, then a row of
// selectable chips. Factored here; Gender stays bespoke (it has a
// locked-prose state, not a chip toggle).

import { For, Show } from "solid-js";
import type { JSX } from "solid-js";
import type { BreakdownBucket } from "~/api/concordanceApi";

export function FilterChipGroup(props: {
  label: string;
  /** Display label of the currently-applied value. Truthy → renders the
   *  "· X" badge and (with `onClear`) the clear link. */
  applied?: string;
  onClear?: () => void;
  buckets: BreakdownBucket[];
  /** Raw value of the selected bucket; clicking it again toggles off. */
  selected?: string;
  /** Chip text for a bucket value. */
  labelFor: (value: string) => string;
  /** Hover-title for a bucket. */
  titleFor: (b: BreakdownBucket) => string;
  onToggle: (value: string | undefined) => void;
  /** Optional footer, e.g. a "+N more" expander. */
  children?: JSX.Element;
}) {
  return (
    <div class="fr-group">
      <div class="fr-label">
        <span>
          {props.label}
          <Show when={props.applied}>
            <span class="applied">· {props.applied}</span>
          </Show>
        </span>
        <Show when={props.applied ? props.onClear : undefined}>
          {(onClear) => (
            <button type="button" class="clr" onClick={() => onClear()()}>
              clear
            </button>
          )}
        </Show>
      </div>
      <div class="fr-opts">
        <For each={props.buckets}>
          {(b) => (
            <span
              class={"fr-opt" + (props.selected === b.value ? " on" : "")}
              onClick={() => props.onToggle(props.selected === b.value ? undefined : b.value)}
              title={props.titleFor(b)}
            >
              {props.labelFor(b.value)}
            </span>
          )}
        </For>
      </div>
      {props.children}
    </div>
  );
}
