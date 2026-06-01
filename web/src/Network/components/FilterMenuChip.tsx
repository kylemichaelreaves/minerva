import { For, Show, createMemo, createSignal } from "solid-js";
import { useClickOutside } from "~/hooks/useClickOutside";
import { useEscape } from "~/hooks/useEscape";

export function FilterMenuChip(props: {
  label: string;
  value: string;
  active: boolean;
  options: { key: string; label: string }[];
  selected: string[];
  onToggle: (key: string) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = createSignal(false);
  let wrapEl: HTMLDivElement | undefined;

  useClickOutside(
    () => wrapEl,
    open,
    () => setOpen(false),
    { event: "mousedown" },
  );

  useEscape(() => setOpen(false), open);

  const selectedSet = createMemo(() => new Set(props.selected));

  return (
    <div class="net-chip-wrap" ref={wrapEl}>
      <button
        class={"net-chip" + (props.active ? " active" : "")}
        onClick={() => setOpen((v) => !v)}
        title={`${props.label} filter`}
      >
        <span class="lbl">{props.label}</span>
        <span class="val">{props.value}</span>
        <span class="caret">▾</span>
      </button>
      <Show when={open()}>
        <div class="net-menu">
          <div class="net-menu-head">
            <span>{props.label}</span>
            <Show when={props.selected.length > 0}>
              <button onClick={props.onClear}>Clear</button>
            </Show>
          </div>
          <div class="net-menu-list">
            <For
              each={props.options}
              fallback={
                <div
                  style={{
                    padding: "8px 10px",
                    color: "var(--ink-mute)",
                    "font-size": "11px",
                  }}
                >
                  No options.
                </div>
              }
            >
              {(opt) => {
                const on = () => selectedSet().has(opt.key);
                return (
                  <button
                    class={"net-menu-item" + (on() ? " on" : "")}
                    onClick={() => props.onToggle(opt.key)}
                  >
                    <span class="mark">{on() ? "✓" : " "}</span>
                    <span>{opt.label}</span>
                    <span class="hint" />
                  </button>
                );
              }}
            </For>
          </div>
        </div>
      </Show>
    </div>
  );
}

/* ============================================================
   Header
   ============================================================ */
