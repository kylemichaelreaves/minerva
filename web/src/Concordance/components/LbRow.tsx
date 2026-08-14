import { Show } from "solid-js";
import type { LemmaIndexRow } from "~/api/concordanceApi";
import { Romanizable } from "~/Concordance/components/Romanizable";
import { Sparkline } from "~/Concordance/components/Sparkline";

export function LbRow(props: { row: LemmaIndexRow; onOpen: () => void }) {
  return (
    <div class="lb-row" onClick={props.onOpen} role="link">
      <span class="rk">{props.row.rank}</span>
      <span class="lem">
        <Romanizable text={props.row.lemma} />
      </span>
      <span class="pos">{props.row.pos.toLowerCase()}</span>
      <span class="ct">{props.row.count.toLocaleString()}</span>
      {/* Two works or more, or there is nothing to compare: a one-work
          distribution renders as a single full-height block on every row, which
          reads as a broken chart rather than as a complete one (#370). The
          fallback keeps the grid track occupied so rows do not reflow when the
          scope widens and the bars come back. */}
      <Show when={props.row.per_work.length > 1} fallback={<span class="spark" />}>
        <Sparkline data={props.row.per_work} />
      </Show>
      <span class="gloss">
        {props.row.distinct_works > 0
          ? `${props.row.distinct_works} work${props.row.distinct_works === 1 ? "" : "s"}`
          : ""}
      </span>
    </div>
  );
}
