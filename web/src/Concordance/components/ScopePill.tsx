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
  scopeAuthors?: string[];
  scopeWorks?: string[];
  onPick: (patch: { scope: ConcScope; scopeAuthors?: string[]; scopeWorks?: string[] }) => void;
}) {
  // One work → its title; multiple → "N works"; none → the "Work" prompt.
  const workLabel = createMemo(() => {
    const works = props.scopeWorks ?? [];
    if (works.length === 0) return "Work";
    if (works.length === 1) return works[0]!;
    return `${works.length} works`;
  });
  // One author → its name; multiple → "N authors"; none → "Author".
  const authorLabel = createMemo(() => {
    const authors = props.scopeAuthors ?? [];
    if (authors.length === 0) return "Author";
    if (authors.length === 1) return authors[0]!;
    return `${authors.length} authors`;
  });
  const steps = createMemo(() => [
    { label: "Corpus", scope: "corpus" as const, cur: props.scope === "corpus" },
    { label: authorLabel(), scope: "author" as const, cur: props.scope === "author" },
    {
      label: workLabel(),
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
                  props.onPick({ scope: "corpus", scopeAuthors: undefined, scopeWorks: undefined });
                  return;
                }
                if (s.scope === "author" && !props.scopeAuthors?.length) return;
                if (s.scope === "work" && !props.scopeWorks?.length) return;
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
