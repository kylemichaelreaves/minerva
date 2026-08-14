import { For, createMemo } from "solid-js";
import type { PerWorkBucket } from "~/api/concordanceApi";

/** How this lemma's occurrences are spread across its top works — one bar per
 *  work, tallest first, heights relative to **this row's own maximum**.
 *
 *  So the tallest bar is always full height. That is intentional (the shape is
 *  the point, not the absolute level) but it also means a single-work
 *  distribution is a single full block, carrying nothing. `LbRow` therefore
 *  draws this only when there are at least two works to compare (#370).
 *
 *  Each bar names its work in the tooltip. It used to show the bare integer,
 *  which was unreadable on its own — and at single-work scope it repeated the
 *  count printed two cells to the left. */
export function Sparkline(props: { data: PerWorkBucket[] }) {
  const maxN = createMemo(() => Math.max(1, ...props.data.map((w) => w.n)));
  return (
    <div class="spark" title="occurrences across this lemma's top works">
      <For each={props.data}>
        {(w) => (
          <span
            class="bar"
            style={{ height: `${Math.max(8, (w.n / maxN()) * 100)}%` }}
            title={`${w.work}: ${w.n.toLocaleString()}`}
          />
        )}
      </For>
    </div>
  );
}
