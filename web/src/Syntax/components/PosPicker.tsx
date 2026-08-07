import { For, Show, createEffect, createMemo, createSignal, onMount } from "solid-js";
import { filterPos, posGloss } from "~/Syntax/corrections/pos";

// Choosing a token's part of speech. Sibling of `RelationPicker`, and
// deliberately the same interaction so the two edits feel like one gesture:
//
// THE FIELD FILTERS; IT NEVER ACCEPTS. What the user types narrows a closed
// inventory and Enter commits the *highlighted row*, never the raw text. Here
// that rule is doing more work than it does for relations: the German parser
// carries a TIGER tag beside the UD one, and `NN` / `PRELS` / `ADJA` are
// shaped exactly like real UD tags, so free text would let the wrong column's
// value through unnoticed. See `corrections/pos.ts` (#253).
//
// Seventeen rows is short enough to show whole, so unlike the relation picker
// there is no scroll-into-view choreography — but the filter stays, because
// typing "prop" is faster than arrowing past eight closed-class tags.

export interface PosPickerProps {
  /** The word being retagged, for the heading. */
  form: string;
  tokenId: number;
  /** The tag as it currently stands. */
  current: string | null;
  onCommit: (upos: string) => void;
  onCancel: () => void;
}

export function PosPicker(props: PosPickerProps) {
  const [query, setQuery] = createSignal("");
  const [cursor, setCursor] = createSignal(0);
  let input: HTMLInputElement | undefined;

  /**
   * The filtered inventory, each tag carrying its position in the flattened
   * list. Computed here rather than counted during render: a mutable counter
   * in JSX survives across re-renders in Solid, so it would drift the moment
   * the filter changed.
   */
  const groups = createMemo(() => {
    let n = 0;
    return filterPos(query()).map((group) => ({
      title: group.title,
      tags: group.tags.map((tag) => ({ ...tag, index: n++ })),
    }));
  });

  const flat = createMemo(() => groups().flatMap((g) => g.tags.map((t) => t.name)));

  // Any keystroke can shorten the list out from under the cursor.
  createEffect(() => {
    const n = flat().length;
    if (cursor() >= n) setCursor(Math.max(0, n - 1));
  });

  onMount(() => {
    input?.focus();
  });

  const commit = () => {
    const picked = flat()[cursor()];
    // No match, no commit.
    if (picked !== undefined) props.onCommit(picked);
  };

  const move = (delta: number) => {
    const n = flat().length;
    if (n === 0) return;
    setCursor((c) => (c + delta + n) % n);
  };

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      move(1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      move(-1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      commit();
    } else if (e.key === "Escape") {
      e.preventDefault();
      props.onCancel();
    }
    // Everything else falls through to the input and filters the list. No
    // window-level capture listener — see the note in RelationPicker for why
    // that breaks Enter.
    e.stopPropagation();
  };

  return (
    <aside
      class="syn-panel syn-pick"
      role="dialog"
      aria-label={`Retag ${props.form}`}
      onKeyDown={onKeyDown}
    >
      <div class="syn-pickq">
        <span class="syn-pickl">Part of speech</span>
        <input
          ref={input}
          value={query()}
          placeholder="filter…"
          aria-label="Filter parts of speech"
          autocomplete="off"
          spellcheck={false}
          onInput={(e) => {
            setQuery(e.currentTarget.value);
            setCursor(0);
          }}
        />
      </div>

      <Show when={props.current}>
        {(current) => (
          <div class="syn-prow syn-cur">
            <span class="syn-rel">{current()}</span>
            <span class="syn-gl">{posGloss(current()) ?? "current"}</span>
          </div>
        )}
      </Show>

      <div class="syn-picklist" role="listbox" aria-label="Parts of speech">
        <For each={groups()}>
          {(group) => (
            <div>
              <div class="syn-pgrp">{group.title}</div>
              <For each={group.tags}>
                {(tag) => (
                  <div
                    class="syn-prow"
                    classList={{ on: cursor() === tag.index }}
                    role="option"
                    aria-selected={cursor() === tag.index}
                    onMouseEnter={() => setCursor(tag.index)}
                    onClick={() => {
                      props.onCommit(tag.name);
                    }}
                  >
                    <span class="syn-rel">{tag.name}</span>
                    <span class="syn-gl">{tag.gloss}</span>
                  </div>
                )}
              </For>
            </div>
          )}
        </For>
        <Show when={flat().length === 0}>
          <div class="syn-pnone">
            No part of speech matches “{query()}”. The list is closed — a TIGER tag like{" "}
            <code>NN</code> cannot be written here.
          </div>
        </Show>
      </div>

      <div class="syn-pickfoot">
        <span>
          {flat().length} of {POS_COUNT} · UD v2
        </span>
        <span class="syn-kbd">↵ commit</span>
      </div>
    </aside>
  );
}

const POS_COUNT = filterPos("").reduce((n, g) => n + g.tags.length, 0);
