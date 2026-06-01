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
//   Escape            — close, return focus to trigger
//   Tab / Shift+Tab   — close, focus moves naturally
//   Printable chars   — type-ahead, 500ms quiet-reset, repeat-key
//                       cycles matches

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
import "~/components/Select.css";

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
  /** Used as the trigger button's id so a wrapping <label for=…>
   *  can target it. */
  id?: string;
  ariaLabel?: string;
  ariaLabelledBy?: string;
  /** Show a clear (×) button inside the trigger when a value is
   *  selected. Clicking calls `onChange("")`. Defaults to true —
   *  set to `false` for selects where a value is required and the
   *  user shouldn't be able to drop back to the placeholder. */
  clearable?: boolean;
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

  // Type-ahead buffer; resets after 500ms of no typing. Lives outside
  // of Solid signals because it's transient input-side state — no
  // reactivity needed.
  let typeBuf = "";
  let typeTimer: number | undefined;

  let triggerRef: HTMLButtonElement | undefined;
  let listboxRef: HTMLUListElement | undefined;
  let panelRef: HTMLDivElement | undefined;
  let rootRef: HTMLDivElement | undefined;

  const selectedIdx = createMemo(() =>
    props.options.findIndex((o) => o.value === props.value),
  );
  const selected = createMemo(() => {
    const i = selectedIdx();
    return i >= 0 ? props.options[i] : undefined;
  });

  // ── Index helpers ─────────────────────────────────────────────────
  const nextEnabledIdx = (from: number, dir: 1 | -1): number => {
    const n = props.options.length;
    if (n === 0) return -1;
    let i = from;
    for (let k = 0; k < n; k++) {
      i = (i + dir + n) % n;
      if (!props.options[i].disabled) return i;
    }
    return -1;
  };
  const firstEnabled = (): number => nextEnabledIdx(-1, 1);
  const lastEnabled = (): number => nextEnabledIdx(0, -1);

  // ── Open / close / commit ─────────────────────────────────────────
  const openPanel = (): void => {
    if (props.disabled || isOpen()) return;
    setOpen(true);
    const sel = selectedIdx();
    setActiveIdx(
      sel >= 0 && !props.options[sel].disabled ? sel : firstEnabled(),
    );
  };

  const closePanel = (returnFocus = true): void => {
    if (!isOpen()) return;
    setOpen(false);
    setActiveIdx(-1);
    typeBuf = "";
    if (returnFocus) triggerRef?.focus();
  };

  const commit = (i: number): void => {
    const o = props.options[i];
    if (o.disabled) return;
    props.onChange(o.value);
    closePanel();
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
    const needle = isRepeat ? typeBuf[0] : typeBuf;
    const n = props.options.length;
    const startBase = activeIdx() < 0 ? 0 : activeIdx();
    const start = isRepeat ? startBase + 1 : startBase;

    for (let k = 0; k < n; k++) {
      const idx = (start + k) % n;
      const o = props.options[idx];
      if (o.disabled) continue;
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
        else setActiveIdx((i) => nextEnabledIdx(i, 1));
        return;

      case "ArrowUp":
        e.preventDefault();
        if (!open) {
          openPanel();
          // Land on the last enabled option, matching native behavior.
          setActiveIdx(lastEnabled());
        } else {
          setActiveIdx((i) => nextEnabledIdx(i, -1));
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
          if (activeIdx() >= 0) commit(activeIdx());
        }
        return;

      case " ":
        if (!open) {
          e.preventDefault();
          openPanel();
        } else if (typeBuf === "") {
          // Space commits when no type-ahead is in flight; otherwise
          // it contributes to the buffer.
          e.preventDefault();
          if (activeIdx() >= 0) commit(activeIdx());
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

    // Printable characters → type-ahead.
    if (e.key.length === 1 && !e.metaKey && !e.ctrlKey && !e.altKey) {
      if (!open) openPanel();
      runTypeahead(e.key);
    }
  };

  const onTriggerClick = (): void => {
    if (props.disabled) return;
    if (isOpen()) closePanel(false);
    else openPanel();
  };

  // Whether the clear-button is visible. Hidden when disabled, when
  // there's no selection, or when the caller explicitly opted out via
  // `clearable={false}`.
  const showClear = createMemo(() => {
    if (props.clearable === false) return false;
    if (props.disabled) return false;
    return selected() !== undefined;
  });

  const onClearClick = (e: MouseEvent): void => {
    // Stop the click from bubbling to the trigger button, which would
    // open / close the panel. We deliberately don't preventDefault on
    // pointerdown because the trigger's click is what we're guarding
    // against; calling stopPropagation on the click event is enough
    // and keeps the focus-state of the trigger predictable.
    e.stopPropagation();
    if (props.disabled) return;
    props.onChange("");
    // If the panel happens to be open when the user clears, close it —
    // they almost certainly want to start over rather than browse the
    // list with a now-empty value.
    if (isOpen()) closePanel(false);
  };

  return (
    <div
      ref={rootRef}
      class={
        "minerva-select" +
        (isOpen() ? " is-open" : "") +
        (props.disabled ? " is-disabled" : "")
      }
    >
      <button
        type="button"
        ref={triggerRef}
        id={baseId}
        class="minerva-select__trigger"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={isOpen()}
        aria-controls={listboxId}
        aria-activedescendant={
          isOpen() && activeIdx() >= 0 ? optionId(activeIdx()) : undefined
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
      </button>

      <Show when={isOpen()}>
        <div class="minerva-select__panel" ref={panelRef}>
          <ul
            ref={listboxRef}
            id={listboxId}
            class="minerva-select__listbox"
            role="listbox"
            tabindex="-1"
          >
            <For each={props.options}>
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
        </div>
      </Show>
    </div>
  );
}
