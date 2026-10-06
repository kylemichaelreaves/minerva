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
            <Show
              when={!s.cur}
              fallback={
                <span class="crumb cur" aria-current="location">
                  {s.label}
                </span>
              }
            >
              <button type="button" class="crumb" onClick={() => props.onPick(s.scope)}>
                {s.label}
              </button>
            </Show>
          </>
        )}
      </For>
      <Show when={props.count !== undefined}>
        <span class="ct">{Number(props.count).toLocaleString()} occurrences</span>
      </Show>
    </span>
  );
}
