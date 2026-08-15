import { Show } from "solid-js";
import type { LemmaIndexRow } from "~/api/concordanceApi";
import { Romanizable } from "~/Concordance/components/Romanizable";
import { Sparkline } from "~/Concordance/components/Sparkline";

export function LbRow(props: {
  row: LemmaIndexRow;
  /** The lemma's own URL. `routeHash` of the `concordance-lemma` route. */
  href: string;
  onOpen: () => void;
}) {
  return (
    // A real anchor, not a `div` with `role="link"` (#375). The row was
    // click-only: no `tabindex`, so it was not in the tab order, and no key
    // handler, so Enter never reached it — while the role told assistive tech
    // there was a link to activate. Opening a lemma is the leaderboard's only
    // action and the lemma text is not itself a control, so there was no
    // alternative path.
    //
    // The anchor goes on the ROW rather than around the cells, so `.lb-row`
    // stays the grid and its six cells stay its direct children. #375 expected
    // this fix to mean re-homing the grid; it does not.
    <a
      class="lb-row"
      href={props.href}
      onClick={(e) => {
        // Let the browser have modified and non-primary clicks — that is what
        // buys open-in-new-tab and middle-click over the old handler.
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
        e.preventDefault();
        props.onOpen();
      }}
    >
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
    </a>
  );
}
