// Single-select dropdown — combobox + listbox pattern with virtual
// focus, so the trigger keeps real keyboard focus while the panel is
// open. Ported from the minerva-select design sketch; tokens come
// from the codebase's `--r-*` system (see Select.css).
//
// Optional `sublabel` per option. None of the project's current
// selects use sublabels — they were the headline feature of the
// design sketch (translator pickers) — but the prop is here for
// future use (TermCard rendering pickers, etc.) without a refactor.
//
// Keyboard model matches the design spec:
//   ArrowDown/ArrowUp — open + move, skipping disabled
//   Home/End          — first/last enabled (when open)
//   Enter             — commit active option
//   Space             — commits when no type-ahead in flight,
//                       otherwise contributes to the buffer
//   Escape            — close, return focus to the control
//   Tab / Shift+Tab   — close, focus moves naturally
//   Printable chars   — type-ahead, 500ms quiet-reset, repeat-key
//                       cycles matches
//
// `filterable` (#363) replaces the last of those: the trigger becomes a text
// input and printable characters narrow the list instead of jumping the
// highlight. Home/End then move the caret, as a reader expects in a field, and
// Space is text rather than a commit. Enter still commits the *highlighted row*
// and never the typed text — see `commitActive`. Three shapes exist; the one
// that surprises people is mobile, and `isMobile` carries the reason.

import {
  For,
  Show,
  createEffect,
  createMemo,
  createSignal,
  onCleanup,
  type JSX,
} from "solid-js";
import { useClickOutside } from "~/hooks/useClickOutside";
import { useMobile } from "~/hooks/useMobile";
import { matchesQuery } from "~/utils/searchFold";
import "~/components/primitives/Select.css";

export interface SelectOption {
  value: string;
  label: string;
  sublabel?: string;
  disabled?: boolean;
}

export interface SelectProps {
  options: SelectOption[];
  /** Controlled value. `undefined` (or `""`) shows the placeholder. */
  value: string | undefined;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  /** Id of the focusable control — the trigger button, or the input when
   *  `filterable` puts one there — so a wrapping <label for=…> can target it. */
  id?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  /** Show a clear (×) button inside the trigger when a value is
   *  selected. Clicking calls `onChange("")`. Defaults to true —
   *  set to `false` for selects where a value is required and the
   *  user shouldn't be able to drop back to the placeholder. */
  clearable?: boolean;
  /** Turn the trigger into a text input that narrows the list as the reader
   *  types, for lists too long to scan — the concordance work picker holds ~964
   *  options (#363). Off by default: the 3-, 5- and 10-option pickers do not
   *  need it, and it changes the keyboard model (see the header comment).
   *
   *  Below 768px the trigger stays a button and the field renders at the top of
   *  the panel instead, because the mobile panel is a full-screen sheet that
   *  would cover the trigger. A filterable trigger shows the selected option's
   *  label but not its `sublabel` — an input cannot hold two lines. */
  filterable?: boolean;
}

let uidCounter = 0;
const nextUid = (): string => `minerva-select-${++uidCounter}`;

export function Select(props: SelectProps): JSX.Element {
  // Capture the id once at mount — the linter flags this as a
  // reactive read outside JSX, but a stable element id is exactly
  // what we want here, not a tracked signal.
  // eslint-disable-next-line solid/reactivity
  const baseId = props.id ?? nextUid();
  const listboxId = `${baseId}-listbox`;
  const optionId = (i: number): string => `${baseId}-opt-${i}`;

  const [isOpen, setOpen] = createSignal(false);
  const [activeIdx, setActiveIdx] = createSignal(-1);
  const [query, setQuery] = createSignal("");

  // Type-ahead buffer; resets after 500ms of no typing. Lives outside
  // of Solid signals because it's transient input-side state — no
  // reactivity needed.
  let typeBuf = "";
  let typeTimer: number | undefined;

  let triggerRef: HTMLButtonElement | undefined;
  let listboxRef: HTMLUListElement | undefined;
  let rootRef: HTMLDivElement | undefined;
  let filterRef: HTMLInputElement | undefined;

  // Viewport-aware, which nothing else in this component is — every other
  // mobile behaviour it has is pure CSS. The reason is measured:
  // `styles/mobile.css:1119-1134` makes the panel a full-screen sheet at
  // `z-index: 80` while `.mobile-sheet` is at 71, so on mobile the panel covers
  // its own trigger. An editable trigger would be typed into blind, so there the
  // trigger stays a button and the field renders inside the panel.
  const isMobile = useMobile();

  /** Desktop `filterable`: the trigger IS the input — the ARIA combobox
   *  pattern, one element rather than a button plus a second field. */
  const fieldTrigger = createMemo(
    () => props.filterable === true && !isMobile(),
  );
  /** Mobile `filterable`: button trigger, field at the top of the sheet. */
  const filterInPanel = createMemo(
    () => props.filterable === true && isMobile(),
  );

  /** The list the panel renders. **Identical to `props.options` — the same array
   *  reference — unless a filterable Select has a non-empty query.** That
   *  identity is what lets every index helper below read `view()` with provably
   *  no behaviour change for the five non-filterable call sites. */
  const view = createMemo<SelectOption[]>(() => {
    const q = query().trim();
    if (props.filterable !== true || q === "") return props.options;
    return props.options.filter((o) => matchesQuery(q, [o.label, o.sublabel]));
  });

  // Resolved against `props.options`, NOT `view()`: the query can exclude the
  // selected option and the trigger still has to show it.
  const selected = createMemo(() =>
    props.options.find((o) => o.value === props.value),
  );

  // ── Index helpers, all view-relative ──────────────────────────────
  const nextEnabledIdx = (from: number, dir: 1 | -1): number => {
    const list = view();
    const n = list.length;
    if (n === 0) return -1;
    let i = from;
    for (let k = 0; k < n; k++) {
      i = (i + dir + n) % n;
      if (!list[i]?.disabled) return i;
    }
    return -1;
  };
  const firstEnabled = (): number => nextEnabledIdx(-1, 1);
  const lastEnabled = (): number => nextEnabledIdx(0, -1);

  /** Where the highlight lands when the panel opens: the current selection if
   *  it is in view and pickable, else the first thing that is. */
  const seedIdx = (): number => {
    const i = view().findIndex(
      (o) => o.value === props.value && o.disabled !== true,
    );
    return i >= 0 ? i : firstEnabled();
  };

  // ── Open / close / commit ─────────────────────────────────────────
  const openPanel = (): void => {
    if (props.disabled || isOpen()) return;
    setOpen(true);
    setActiveIdx(seedIdx());
  };

  const closePanel = (returnFocus = true): void => {
    if (!isOpen()) return;
    setOpen(false);
    setActiveIdx(-1);
    typeBuf = "";
    // Every open starts from the full list. All close paths funnel through
    // here, so there is no route that leaves a stale query behind.
    setQuery("");
    // In the field shape the input IS the trigger, so that is where focus
    // belongs on close.
    if (returnFocus) (fieldTrigger() ? filterRef : triggerRef)?.focus();
  };

  const commit = (i: number): void => {
    const o = view()[i];
    if (o === undefined || o.disabled) return;
    props.onChange(o.value);
    closePanel();
  };

  const moveActive = (dir: 1 | -1): void => {
    setActiveIdx((i) => nextEnabledIdx(i, dir));
  };
  const commitActive = (): void => {
    // The field filters; it never accepts. There is no path from the query
    // text to `onChange` — nothing highlighted means nothing committed.
    if (activeIdx() >= 0) commit(activeIdx());
  };

  useClickOutside(
    () => rootRef,
    isOpen,
    () => closePanel(false),
    { event: "pointerdown", capture: true },
  );

  // Keep the active option in view.
  // scrollIntoView so the *page* never scrolls when arrowing through
  // a select that's near the viewport edge — only the listbox moves.
  createEffect(() => {
    if (!isOpen()) return;
    const i = activeIdx();
    if (i < 0 || !listboxRef) return;
    const el = listboxRef.children[i] as HTMLElement | undefined;
    if (!el) return;
    const top = el.offsetTop;
    const bottom = top + el.offsetHeight;
    const viewTop = listboxRef.scrollTop;
    const viewBottom = viewTop + listboxRef.clientHeight;
    if (top < viewTop) listboxRef.scrollTop = top;
    else if (bottom > viewBottom)
      listboxRef.scrollTop = bottom - listboxRef.clientHeight;
  });

  // The list can shorten under the highlight from either side: a keystroke
  // narrows it, and so does the caller (picking a work removes it from
  // `addWorkOptions`; a language switch replaces the list wholesale). An
  // activeIdx past the end makes Enter a silent no-op and names an
  // `aria-activedescendant` that does not exist.
  //
  // No `isOpen()` guard: activeIdx is -1 while closed and `-1 >= n` is false,
  // so this self-neutralises. The updater form reads the current value without
  // subscribing to it, so it cannot loop.
  createEffect(() => {
    const n = view().length;
    const fallback = n === 0 ? -1 : firstEnabled();
    setActiveIdx((i) => (i >= n ? fallback : i));
  });

  // No focus-on-open effect. In the field shape the input already holds focus
  // (it is the trigger, and the click handler focuses it); on mobile we
  // deliberately do NOT auto-focus, because raising the soft keyboard over a
  // full-screen list costs more than the one tap it saves.

  onCleanup(() => {
    if (typeTimer !== undefined) clearTimeout(typeTimer);
  });

  // ── Type-ahead ────────────────────────────────────────────────────
  const runTypeahead = (ch: string): void => {
    typeBuf += ch.toLowerCase();
    if (typeTimer !== undefined) clearTimeout(typeTimer);
    typeTimer = window.setTimeout(() => {
      typeBuf = "";
      typeTimer = undefined;
    }, 500);

    // If the buffer is one repeated character ("j", "jj", "jjj"),
    // advance to the NEXT match — lets users cycle through matches
    // by tapping the same key.
    const isRepeat = typeBuf.length > 1 && /^(.)\1+$/.test(typeBuf);
    const needle = isRepeat ? typeBuf.charAt(0) : typeBuf;
    const n = props.options.length;
    const startBase = activeIdx() < 0 ? 0 : activeIdx();
    const start = isRepeat ? startBase + 1 : startBase;

    for (let k = 0; k < n; k++) {
      const idx = (start + k) % n;
      // `props.options`, not `view()`, and safely so: type-ahead is only
      // reachable when `filterable` is off, where the two are the same array.
      const o = props.options[idx];
      if (o === undefined || o.disabled) continue;
      if (o.label.toLowerCase().startsWith(needle)) {
        setActiveIdx(idx);
        return;
      }
    }
  };

  // ── Trigger keydown ───────────────────────────────────────────────
  const onTriggerKeyDown = (e: KeyboardEvent): void => {
    if (props.disabled) return;
    const open = isOpen();

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        if (!open) openPanel();
        else moveActive(1);
        return;

      case "ArrowUp":
        e.preventDefault();
        if (!open) {
          openPanel();
          // Land on the last enabled option, matching native behavior.
          setActiveIdx(lastEnabled());
        } else {
          moveActive(-1);
        }
        return;

      case "Home":
        if (open) {
          e.preventDefault();
          setActiveIdx(firstEnabled());
        }
        return;

      case "End":
        if (open) {
          e.preventDefault();
          setActiveIdx(lastEnabled());
        }
        return;

      case "Enter":
        if (open) {
          e.preventDefault();
          commitActive();
        }
        return;

      case " ":
        if (!open) {
          e.preventDefault();
          openPanel();
        } else if (typeBuf === "") {
          // Space commits when no type-ahead is in flight; otherwise
          // it contributes to the buffer. In filterable mode `typeBuf` is
          // permanently "", and this arm is unreachable anyway because focus
          // is in the field.
          e.preventDefault();
          commitActive();
        } else {
          runTypeahead(" ");
        }
        return;

      case "Escape":
        if (open) {
          e.preventDefault();
          closePanel();
        }
        return;

      case "Tab":
        // Don't preventDefault — let the browser move focus naturally.
        if (open) closePanel(false);
        return;
    }

    // Printable characters → type-ahead, or the filter field.
    if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) {
      // No seeding branch. This handler only runs for the button trigger, and
      // in `filterable` mode that shape only exists on mobile, where there is
      // no hardware keyboard to type on a closed select. On desktop the input
      // IS the trigger, so the character lands natively.
      if (!open) openPanel();
      runTypeahead(e.key);
    }
  };

  /** The field owns the keys that drive the list while it has focus. Home/End
   *  are deliberately absent: in a text field those move the caret, which is
   *  what a reader expects. */
  const onFilterKeyDown = (e: KeyboardEvent): void => {
    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        moveActive(1);
        return;
      case "ArrowUp":
        e.preventDefault();
        moveActive(-1);
        return;
      case "Enter":
        e.preventDefault();
        commitActive();
        return;
      case "Escape":
        e.preventDefault();
        closePanel();
        return;
      case "Tab":
        // No preventDefault — focus returns to the trigger and then moves on
        // naturally. Leaving focus in an unmounting node drops it to <body>.
        closePanel();
        return;
    }
  };

  const onFilterInput = (e: InputEvent): void => {
    setQuery((e.currentTarget as HTMLInputElement).value);
    // Typing into a closed field opens the list — the reader is already saying
    // what they want, so making them click as well is pure friction.
    openPanel();
    // Every keystroke re-aims the highlight at the top of what now matches.
    setActiveIdx(firstEnabled());
  };

  /** The input's displayed text. It does double duty in the field shape: the
   *  query while the list is open, the selected option's label at rest. Closing
   *  clears the query, so the label comes back on its own. */
  const fieldValue = (): string =>
    fieldTrigger() && !isOpen() ? (selected()?.label ?? "") : query();

  const emptyText = (): string =>
    query() === "" ? "No options" : `No match for “${query()}”`;

  const onTriggerClick = (): void => {
    if (props.disabled) return;
    if (isOpen()) closePanel(false);
    else openPanel();
  };

  /** Clicking the input opens the list — it does not toggle, because clicking
   *  into a text field to place the caret must not close the list under it.
   *  The enclosing <label> forwards a click on the trigger's padding here. */
  const onFieldClick = (): void => {
    openPanel();
  };

  // Whether the clear-button is visible. Hidden when disabled, when
  // there's no selection, or when the caller explicitly opted out via
  // `clearable={false}`.
  const showClear = createMemo(() => {
    if (props.clearable === false) return false;
    if (props.disabled) return false;
    return selected() !== undefined;
  });

  /** Shared by the pointer and keyboard paths so the two cannot drift.
   *
   *  Deliberately does not re-check `props.disabled`: `showClear()` above is
   *  the single owner of that rule, and the `<Show>` it gates swaps in the
   *  caret fallback, so while disabled there is no element for either handler
   *  to be bound to — not for a pointer, not for assistive tech, not for a
   *  programmatic `.click()`. A second copy here was unreachable and left its
   *  false branch permanently uncovered on a gate that counts branches
   *  (#478, #250). The invariant it stood in for is pinned by
   *  "a disabled Select with a value renders no clear control" in
   *  tests/Select.test.tsx. */
  const clearSelection = (): void => {
    props.onChange("");
    // If the panel happens to be open when the user clears, close it —
    // they almost certainly want to start over rather than browse the
    // list with a now-empty value.
    if (isOpen()) closePanel(false);
  };

  // `role="button"` without key handling is mouse-only (typescript:S1082).
  // The span carries `tabindex="-1"` so it is not a tab stop, but it is still
  // reachable programmatically and by assistive tech, both of which expect the
  // two activation keys a native button answers.
  const onClearKeyDown = (e: KeyboardEvent): void => {
    if (e.key !== "Enter" && e.key !== " ") return;
    e.preventDefault();
    e.stopPropagation();
    clearSelection();
  };

  const onClearClick = (e: MouseEvent): void => {
    // Stop the click from bubbling to the trigger, which would open / close
    // the panel. We deliberately don't preventDefault on pointerdown because
    // the trigger's click is what we're guarding against; calling
    // stopPropagation on the click event is enough and keeps the focus-state
    // of the trigger predictable.
    //
    // In the field shape the trigger is a <label>, so this guard does a second
    // job: without it the click would reach the label, the browser would
    // forward its own click to the labelled input, and `onFieldClick` would
    // re-open the panel this handler just closed. Not reachable today — no
    // caller combines `filterable` with a clearable value — and not testable in
    // jsdom either, which does not implement label activation.
    e.stopPropagation();
    clearSelection();
  };

  /** One set of props, spread into whichever site renders the field, so the
   *  two shapes cannot drift and neither is a copy of the other. */
  const fieldProps = () => ({
    ref: (el: HTMLInputElement) => (filterRef = el),
    type: "text",
    class: "minerva-select__filter-input",
    role: "combobox" as const,
    "aria-expanded": isOpen(),
    "aria-controls": listboxId,
    "aria-activedescendant":
      isOpen() && activeIdx() >= 0 ? optionId(activeIdx()) : undefined,
    "aria-autocomplete": "list" as const,
    "aria-label": props.ariaLabel,
    "aria-labelledby": props.ariaLabelledBy,
    autocomplete: "off",
    spellcheck: false,
    placeholder: props.placeholder ?? "Select…",
    value: fieldValue(),
    disabled: props.disabled,
    onClick: onFieldClick,
    onInput: onFilterInput,
    onKeyDown: onFilterKeyDown,
  });

  /** Caret by default, clear (×) when there is a value. Shared verbatim by
   *  both trigger shapes — only one renders at a time. */
  const affordance = (): JSX.Element => (
    <>
        {/* Right-side affordance: caret by default, clear (×) button
            when a value is selected and `clearable` isn't disabled.
            The clear button REPLACES the caret rather than appearing
            beside it — fewer competing glyphs in the right rail, and
            the trigger remains clickable everywhere outside the ×
            (so the user can still re-open the panel by clicking the
            label, just not by clicking the × itself). */}
        <Show
          when={showClear()}
          fallback={
            <span class="minerva-select__caret" aria-hidden="true">
              <svg viewBox="0 0 10 6" width="10" height="6">
                <path
                  d="M1 1l4 4 4-4"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.25"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </span>
          }
        >
          {/* Span with role=button (not <button>) — the combobox
              trigger is already a <button>, and nested native buttons
              are invalid HTML + cause hydration warnings. */}
          <span
            class="minerva-select__clear"
            role="button"
            tabindex="-1"
            aria-label="Clear selection"
            onClick={onClearClick}
            onKeyDown={onClearKeyDown}
            onPointerDown={(e) => {
              // Prevent the trigger from grabbing focus before our
              // click fires; without this, in some browsers the
              // click target races with the focus shift and the
              // panel opens momentarily before clearing.
              e.stopPropagation();
            }}
          >
            <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true">
              <path
                d="M1 1l8 8M9 1l-8 8"
                fill="none"
                stroke="currentColor"
                stroke-width="1.25"
                stroke-linecap="round"
              />
            </svg>
          </span>
        </Show>
    </>
  );

  return (
    <div
      ref={rootRef}
      class={
        "minerva-select" +
        (isOpen() ? " is-open" : "") +
        (props.disabled ? " is-disabled" : "")
      }
    >
      <Show when={fieldTrigger()} fallback={
              <button
                type="button"
                ref={triggerRef}
                id={baseId}
                class="minerva-select__trigger"
                // Plain button whenever the panel hosts the field (mobile), because
                // the field claims `role="combobox"` there and two elements claiming it
                // is invalid. `aria-activedescendant` is only announced on the focused
                // element, so it goes wherever focus is.
                role={filterInPanel() ? "button" : "combobox"}
                aria-haspopup="listbox"
                aria-expanded={isOpen()}
                aria-controls={listboxId}
                aria-activedescendant={
                  !filterInPanel() && isOpen() && activeIdx() >= 0
                    ? optionId(activeIdx())
                    : undefined
                }
                aria-label={props.ariaLabel}
                aria-labelledby={props.ariaLabelledBy}
                aria-disabled={props.disabled || undefined}
                disabled={props.disabled}
                onClick={onTriggerClick}
                onKeyDown={onTriggerKeyDown}
              >
                <span class="minerva-select__value">
                  <Show
                    when={selected()}
                    fallback={
                      <span class="minerva-select__placeholder">
                        {props.placeholder ?? "Select…"}
                      </span>
                    }
                  >
                    {(s) => (
                      <>
                        <span class="minerva-select__primary">{s().label}</span>
                        <Show when={s().sublabel}>
                          {(sub) => (
                            <span class="minerva-select__secondary">{sub()}</span>
                          )}
                        </Show>
                      </>
                    )}
                  </Show>
                </span>
                {affordance()}
              </button>}>
        {/* The trigger IS the input (#363). A wrapper is structurally forced:
            an <input> cannot contain children, and the caret and the clear ×
            must stay inside the trigger — `styles/mobile.css:973-985` styles the
            Refs active-filter chip with `:has(.minerva-select__clear)` scoped to
            it, and moving the × out would silently stop that matching.

            A <label> rather than a <div>, so clicking the wrapper's padding
            focuses the input *natively*. The first cut hung an `onClick` on a
            div to do that by hand, which is a non-native interactive element
            with no keyboard path — Sonar's S6848 and S1082, and a fair call.
            The label needs no handler at all: the click reaches the input, and
            the input's own onClick opens the panel.

            Do not let a caller nest this inside another <label>.
            `features/Refs/components/RefsFilterField.tsx` wraps Select in a bare one, so
            it must never set `filterable` — there is a test on that. */}
        <label class="minerva-select__trigger minerva-select__trigger--field">
          <input id={baseId} {...fieldProps()} />
          {affordance()}
        </label>
      </Show>

      <Show when={isOpen()}>
        <div class="minerva-select__panel">
          <Show when={filterInPanel()}>
            <div class="minerva-select__filter">
              <input {...fieldProps()} />
            </div>
          </Show>

          {/* INVARIANT: this <ul>'s children are exactly `view()`, 1:1. The
              scroll effect above indexes `listboxRef.children[activeIdx()]`,
              so nothing else may live in here — the empty state and the
              footer are siblings below, inside the panel. */}
          <ul
            ref={listboxRef}
            id={listboxId}
            class="minerva-select__listbox"
            role="listbox"
            tabindex="-1"
          >
            <For each={view()}>
              {(opt, i) => {
                const isActive = (): boolean => i() === activeIdx();
                const isSelected = (): boolean => opt.value === props.value;
                return (
                  <li
                    id={optionId(i())}
                    role="option"
                    aria-selected={isSelected()}
                    aria-disabled={opt.disabled || undefined}
                    class={
                      "minerva-select__option" +
                      (isActive() ? " is-active" : "") +
                      (isSelected() ? " is-selected" : "") +
                      (opt.disabled ? " is-disabled" : "")
                    }
                    onPointerDown={(e) => {
                      // Keep focus on the trigger so the combobox
                      // pattern (aria-activedescendant) stays intact.
                      e.preventDefault();
                      if (!opt.disabled) commit(i());
                    }}
                    onPointerEnter={() => {
                      if (!opt.disabled) setActiveIdx(i());
                    }}
                  >
                    <span class="minerva-select__option-text">
                      <span class="minerva-select__primary">{opt.label}</span>
                      <Show when={opt.sublabel}>
                        {(sub) => (
                          <span class="minerva-select__secondary">
                            {sub()}
                          </span>
                        )}
                      </Show>
                    </span>
                  </li>
                );
              }}
            </For>
          </ul>

          <Show when={props.filterable === true && view().length === 0}>
            <div class="minerva-select__empty">{emptyText()}</div>
          </Show>
          <Show when={props.filterable === true}>
            <div class="minerva-select__foot">
              {view().length} of {props.options.length}
            </div>
          </Show>
        </div>
      </Show>
    </div>
  );
}
