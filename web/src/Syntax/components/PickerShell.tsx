import { For, Show, createEffect, createMemo, createSignal, onMount } from "solid-js";

// The filter-and-commit picker both correction pickers are built from.
//
// THE FIELD FILTERS; IT NEVER ACCEPTS. What the user types narrows a closed
// inventory and Enter commits the *highlighted row*, never the raw text. If
// nothing matches there is nothing to commit. That rule is the reason this
// component exists once rather than twice: a mistyped relation and a pasted
// TIGER tag are both silent data corruption — they validate, they export, and
// they are wrong — and encoding the guard in one place is the only way both
// pickers keep it.
//
// Extracted from `RelationPicker` when `PosPicker` arrived and duplicated it
// wholesale (#253). Fixing the accessibility of the list in one place was the
// other half of the reason: the row markup needed focusable options and a
// keyboard path, and doing that twice would have meant doing it differently.

export interface PickerRow {
  /** The value written to storage. */
  name: string;
  /** One-line gloss, shown beside the name. */
  gloss: string;
}

export interface PickerGroup {
  title: string;
  rows: PickerRow[];
}

export interface PickerShellProps {
  /** Field label above the filter input — "Relation", "Part of speech". */
  label: string;
  /** Announced name of the dialog, e.g. `Relabel Geist`. */
  dialogLabel: string;
  /** Announced name of the filter input, e.g. `Filter relations`. */
  filterLabel: string;
  /** Announced name of the list. */
  listLabel: string;
  /** The inventory, already filtered by `query`. */
  groups: (query: string) => PickerGroup[];
  /** The value as it currently stands, shown pinned above the list. */
  current: string | null;
  /** Gloss for `current`, when there is one. */
  currentGloss?: string;
  /** Total inventory size, for the "n of N" footer. */
  total: number;
  /** Shown when the filter matches nothing. Names what cannot be written. */
  emptyHint: (query: string) => import("solid-js").JSX.Element;
  /** Trailing footer note, e.g. "UD v2 · German-HDT profile". */
  footNote: string;
  onCommit: (name: string) => void;
  onCancel: () => void;
}

export function PickerShell(props: PickerShellProps) {
  const [query, setQuery] = createSignal("");
  const [cursor, setCursor] = createSignal(0);
  let input: HTMLInputElement | undefined;
  let listEl: HTMLDivElement | undefined;

  /**
   * The filtered inventory, each row carrying its position in the flattened
   * list.
   *
   * Computed here rather than counted during render: a mutable counter in JSX
   * survives across re-renders in Solid — the component body runs once and
   * only the reactive parts re-execute — so it would drift the moment the
   * filter changed.
   */
  const groups = createMemo(() => {
    let n = 0;
    return props.groups(query()).map((group) => ({
      title: group.title,
      rows: group.rows.map((row) => ({ ...row, index: n++ })),
    }));
  });

  /** Just the names, in cursor order. */
  const flat = createMemo(() => groups().flatMap((g) => g.rows.map((r) => r.name)));

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
    // Keep the highlighted row in view when arrowing past the fold. Purely
    // cosmetic, and guarded: `scrollIntoView` is absent in jsdom, where an
    // unguarded call threw out of the microtask — an unhandled rejection that
    // vitest reports without failing the test that caused it.
    queueMicrotask(() => {
      const row = listEl?.querySelector(".syn-prow.on");
      if (row instanceof Element && typeof row.scrollIntoView === "function") {
        row.scrollIntoView({ block: "nearest" });
      }
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
    //
    // No window-level key handling here. An earlier version registered a
    // capture-phase listener to stop the overlay's shortcuts from firing while
    // the picker is open — but capture runs *before* the target, so
    // `stopPropagation` there prevented this component's own handler from ever
    // running and Enter silently did nothing. The overlay already ignores keys
    // while a picker is open, which is the right place for that.
    e.stopPropagation();
  };

  /** Commit from the keyboard on a focused row, for parity with the click. */
  const onRowKeyDown = (e: KeyboardEvent, name: string) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      props.onCommit(name);
    }
  };

  return (
    // A real <dialog>, not `role="dialog"`: the element carries the semantics
    // on every device, and screen readers on mobile do not honour the role on
    // a bare <aside>. `open` because mounting *is* the open state here —
    // the parent unmounts the component to close it.
    <dialog class="syn-panel syn-pick" open aria-label={props.dialogLabel} onKeyDown={onKeyDown}>
      <div class="syn-pickq">
        <span class="syn-pickl">{props.label}</span>
        <input
          ref={input}
          value={query()}
          placeholder="filter…"
          aria-label={props.filterLabel}
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
            <span class="syn-gl">{props.currentGloss ?? "current"}</span>
          </div>
        )}
      </Show>

      <div class="syn-picklist" ref={listEl} role="listbox" aria-label={props.listLabel}>
        <For each={groups()}>
          {(group) => (
            <div>
              <div class="syn-pgrp">{group.title}</div>
              <For each={group.rows}>
                {(row) => (
                  // `tabindex="-1"` so the option is focusable — an
                  // `option` role that cannot take focus is unreachable to a
                  // screen reader driving the list directly. Focus still
                  // lives in the filter input during normal use; the arrow
                  // keys move `cursor`, not focus.
                  <div
                    class="syn-prow"
                    classList={{ on: cursor() === row.index }}
                    role="option"
                    tabindex={-1}
                    aria-selected={cursor() === row.index}
                    onMouseEnter={() => setCursor(row.index)}
                    onKeyDown={(e) => onRowKeyDown(e, row.name)}
                    onClick={() => {
                      props.onCommit(row.name);
                    }}
                  >
                    <span class="syn-rel">{row.name}</span>
                    <span class="syn-gl">{row.gloss}</span>
                  </div>
                )}
              </For>
            </div>
          )}
        </For>
        <Show when={flat().length === 0}>
          <div class="syn-pnone">{props.emptyHint(query())}</div>
        </Show>
      </div>

      <div class="syn-pickfoot">
        <span>
          {flat().length} of {props.total} · {props.footNote}
        </span>
        <span class="syn-kbd">↵ commit</span>
      </div>
    </dialog>
  );
}
