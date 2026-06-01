import { Show, createMemo } from "solid-js";
import type { LemmaIndexRow } from "~/api/concordanceApi";
import { Sparkline } from "~/Concordance/components/Sparkline";

export function LbRow(props: { row: LemmaIndexRow; onOpen: () => void }) {
  const sparkData = createMemo(() => props.row.per_work.map((w) => w.n));
  return (
    <div class="lb-row" onClick={props.onOpen} role="link">
      <span class="rk">{props.row.rank}</span>
      <span class="lem">{props.row.lemma}</span>
      <span class="pos">{props.row.pos.toLowerCase()}</span>
      <span class="ct">{props.row.count.toLocaleString()}</span>
      <Show when={props.row.per_work.length > 0} fallback={<span class="spark" />}>
        <Sparkline data={sparkData()} />
      </Show>
      <span class="gloss">
        {props.row.distinct_works > 0
          ? `${props.row.distinct_works} work${props.row.distinct_works === 1 ? "" : "s"}`
          : ""}
      </span>
    </div>
  );
}
