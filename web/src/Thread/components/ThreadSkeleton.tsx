import { For } from "solid-js";

export function ThreadSkeleton() {
  const SKELETON_LINES = ["96%", "88%", "92%", "74%"];
  return (
    <div class="thread-skeleton" aria-busy="true" aria-live="polite">
      <span class="sr-only">Loading conversation…</span>
      <div class="turn turn-user skeleton-turn">
        <div class="skeleton-meta" />
        <div class="skeleton-body">
          <div class="skeleton-line" style={{ width: "62%" }} />
        </div>
      </div>
      <div class="turn turn-minerva skeleton-turn">
        <div class="skeleton-meta wide" />
        <div class="skeleton-body">
          <For each={SKELETON_LINES}>
            {(w) => <div class="skeleton-line" style={{ width: w }} />}
          </For>
        </div>
      </div>
    </div>
  );
}
