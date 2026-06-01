import { For, Show, createMemo } from "solid-js";
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
        <span class="ct">{props.count!.toLocaleString()} occurrences</span>
      </Show>
    </span>
  );
}

export function ScopePillDetail(props: {
  scope: ConcScope;
  scopeAuthor?: string;
  scopeWork?: string;
  onPick: (patch: { scope: ConcScope; scopeAuthor?: string; scopeWork?: string }) => void;
}) {
  const steps = createMemo(() => [
    { label: "Corpus", scope: "corpus" as const, cur: props.scope === "corpus" },
    { label: props.scopeAuthor ?? "Author", scope: "author" as const, cur: props.scope === "author" },
    {
      label: props.scopeWork ?? "Work",
      scope: "work" as const,
      cur: props.scope === "work",
    },
  ]);
  return (
    <span class="scope-pill">
      <For each={steps()}>
        {(s, i) => (
          <>
            <Show when={i() > 0 && !s.cur}>
              <span class="arr">›</span>
            </Show>
            <span
              class={"crumb" + (s.cur ? " cur" : "")}
              onClick={() => {
                if (s.cur) return;
                if (s.scope === "corpus") {
                  props.onPick({ scope: "corpus", scopeAuthor: undefined, scopeWork: undefined });
                  return;
                }
                if (s.scope === "author" && !props.scopeAuthor) return;
                if (s.scope === "work" && !props.scopeWork) return;
                props.onPick({ scope: s.scope });
              }}
            >
              {s.label}
            </span>
          </>
        )}
      </For>
    </span>
  );
}
