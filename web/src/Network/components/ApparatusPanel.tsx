import { For, Show } from "solid-js";
import type { ApparatusSourceRow } from "~/api/networkApi";

/** Citations made in editors', translators' and transcribers' apparatus
 *  (#710). They are credited to that person, which keeps them off the
 *  author axis the matrix, arcs and heatmap draw — so this list is where
 *  the page credits them, next to the author whose work hosts the notes. */
export function ApparatusPanel(props: { rows: ApparatusSourceRow[] }) {
  return (
    <Show when={props.rows.length > 0}>
      <div class="net-panel">
        <div class="net-panel-head">
          <div>
            <div class="net-panel-title">Editors &amp; translators</div>
            <div class="net-panel-q">Whose notes are doing the citing?</div>
          </div>
        </div>
        <div class="net-panel-body">
          <div class="net-leader-wrap">
            <div class="net-leader-rows">
              <For each={props.rows}>
                {(row) => (
                  <div class="net-leader-row" data-testid="apparatus-row">
                    <div class="work">
                      {row.name}
                      <span class="auth"> in {row.host_author}</span>
                    </div>
                    <div class="cnt">{row.n.toLocaleString()}</div>
                  </div>
                )}
              </For>
            </div>
          </div>
        </div>
      </div>
    </Show>
  );
}
