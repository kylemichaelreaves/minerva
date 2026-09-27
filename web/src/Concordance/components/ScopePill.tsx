import { For, Show } from "solid-js";
import type { ConcScope } from "~/api/concordanceApi";

export function ScopePill(props: {
  steps: { label: string; scope: ConcScope; cur: boolean }[];
  count?: number;
  onPick: (s: ConcScope) => void;
}) {
  return (
    <span class="scope-pill">
      <For each={props.steps}>
        {(s, i) => (
          <>
            <Show when={i() > 0 && !s.cur}>
              <span class="arr">‹</span>
            </Show>
            <span
              class={"crumb" + (s.cur ? " cur" : "")}
              onClick={() => !s.cur && props.onPick(s.scope)}
            >
              {s.label}
            </span>
          </>
        )}
      </For>
      <Show when={props.count !== undefined}>
        <span class="ct">{Number(props.count).toLocaleString()} occurrences</span>
      </Show>
    </span>
  );
}
