import { createSignal, Show } from "solid-js";
import type { JSX } from "@solidjs/web";

interface Props {
  /** What is hidden, in the reader's words — "Editorial Introduction". */
  label: string;
  /** How many chunks are inside, so the reader can judge before opening. */
  count: number;
  children: JSX.Element;
}

/**
 * A run of editors' apparatus, collapsed by default.
 *
 * The Reader's first collapsible block. Apparatus is real scholarship and is
 * kept, but it is not Hegel — presenting it inline is what made the corpus
 * misleading (#534). Closed by default states the priority: the author first,
 * the editors on request.
 *
 * Open/closed is per-viewer UI state and deliberately not persisted; it says
 * nothing about the corpus.
 */
export function EditorialBlock(props: Props) {
  const [open, setOpen] = createSignal(false);
  return (
    <div class="editorial-block" data-open={open() ? "" : undefined}>
      <button
        type="button"
        class="editorial-block-summary"
        aria-expanded={open() ? "true" : "false"}
        onClick={() => setOpen(!open())}
      >
        <span class="editorial-block-caret" aria-hidden="true">
          {open() ? "▾" : "▸"}
        </span>
        <span class="editorial-block-label">{props.label}</span>
        <span class="editorial-block-count">
          {props.count} {props.count === 1 ? "section" : "sections"}
        </span>
      </button>
      <Show when={open()}>
        <div class="editorial-block-body">{props.children}</div>
      </Show>
    </div>
  );
}
