import { For, createMemo } from "solid-js";

export function Sparkline(props: { data: number[] }) {
  const maxN = createMemo(() => Math.max(1, ...props.data));
  return (
    <div class="spark">
      <For each={props.data}>
        {(v) => (
          <span
            class="bar"
            style={{ height: `${Math.max(8, (v / maxN()) * 100)}%` }}
            title={String(v)}
          />
        )}
      </For>
    </div>
  );
}
