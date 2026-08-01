import { For, Show, createEffect, createMemo, createSignal, onMount } from "solid-js";
import { filterRelations, relationGloss } from "~/Syntax/corrections/relations";

// Frame 07. Choosing the relation on an arc.
//
// THE FIELD FILTERS; IT NEVER ACCEPTS. A mistyped relation is silent data
// corruption — it validates, it exports, and it is wrong, and nothing
// downstream will ever tell you. So what the user types narrows a closed
// inventory and Enter commits the *highlighted row*, never the raw text. If
// nothing matches, there is nothing to commit.
//
// The inventory carries both subtype families (`obj` and `expl:pv`, `acl` and
// `acl:relcl`) because Stanza's German is GSD-trained while the corrected
// trees are HDT-style — the machine writes one and the corrector reaches for
// the other. See `corrections/relations.ts`.

export interface RelationPickerProps {
  /** The word being relabelled, for the heading. */
  form: string;
  tokenId: number;
  /** The word it attaches to; absent when it is the root. */
  headForm?: string;
  headId?: number;
  /** The relation as it currently stands. */
  current: string | null;
  onCommit: (relation: string) => void;
  onCancel: () => void;
}

export function RelationPicker(props: RelationPickerProps) {
  const [query, setQuery] = createSignal("");
  const [cursor, setCursor] = createSignal(0);
  let input: HTMLInputElement | undefined;
  let listEl: HTMLDivElement | undefined;

  /**
   * The filtered inventory, each relation carrying its position in the
   * flattened list.
   *
   * Computed here rather than counted during render: a mutable counter in JSX
   * survives across re-renders in Solid — the component body runs once and
   * only the reactive parts re-execute — so it would drift the moment the
   * filter changed.
   */
  const groups = createMemo(() => {
    let n = 0;
    return filterRelations(query()).map((group) => ({
      title: group.title,
      relations: group.relations.map((relation) => ({ ...relation, index: n++ })),
    }));
  });

  /** Just the names, in cursor order. */
  const flat = createMemo(() => groups().flatMap((g) => g.relations.map((r) => r.name)));

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
    // No match, no commit. The one thing this component must never do is
    // accept what was typed.
    if (picked !== undefined) props.onCommit(picked);
  };

  const move = (delta: number) => {
    const n = flat().length;
    if (n === 0) return;
    setCursor((c) => (c + delta + n) % n);
    // Keep the highlighted row in view when arrowing past the fold.
    queueMicrotask(() => {
      listEl?.querySelector(".syn-prow.on")?.scrollIntoView({ block: "nearest" });
    });
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
    // Everything else falls through to the input and filters the list.
    e.stopPropagation();
  };

  // No window-level key handling here. An earlier version registered a
  // capture-phase listener to stop the overlay's shortcuts from firing while
  // the picker is open — but capture runs *before* the target, so
  // `stopPropagation` there prevented this component's own `onKeyDown` from
  // ever running and Enter silently did nothing. The overlay already ignores
  // keys while `picking()` is true, which is the right place for that.

  return (
    <aside
      class="syn-panel syn-pick"
      role="dialog"
      aria-label={`Relabel ${props.form}`}
      onKeyDown={onKeyDown}
    >
      <div class="syn-pickq">
        <span class="syn-pickl">Relation</span>
        <input
          ref={input}
          value={query()}
          placeholder="filter…"
          aria-label="Filter relations"
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
            <span class="syn-gl">{relationGloss(current()) ?? "current"}</span>
          </div>
        )}
      </Show>

      <div class="syn-picklist" ref={listEl} role="listbox" aria-label="Relations">
        <For each={groups()}>
          {(group) => (
            <div>
              <div class="syn-pgrp">{group.title}</div>
              <For each={group.relations}>
                {(relation) => (
                  <div
                    class="syn-prow"
                    classList={{ on: cursor() === relation.index }}
                    role="option"
                    aria-selected={cursor() === relation.index}
                    onMouseEnter={() => setCursor(relation.index)}
                    onClick={() => {
                      props.onCommit(relation.name);
                    }}
                  >
                    <span class="syn-rel">{relation.name}</span>
                    <span class="syn-gl">{relation.gloss}</span>
                  </div>
                )}
              </For>
            </div>
          )}
        </For>
        <Show when={flat().length === 0}>
          <div class="syn-pnone">
            No relation matches “{query()}”. The list is closed — nothing outside it can be
            written.
          </div>
        </Show>
      </div>

      <div class="syn-pickfoot">
        <span>
          {flat().length} of {RELATION_COUNT} · UD v2 · German-HDT profile
        </span>
        <span class="syn-kbd">↵ commit</span>
      </div>
    </aside>
  );
}

const RELATION_COUNT = filterRelations("").reduce((n, g) => n + g.relations.length, 0);
