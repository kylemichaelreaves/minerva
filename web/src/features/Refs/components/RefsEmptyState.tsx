import { Show } from "solid-js";

export function RefsEmptyState(props: { hasFilters: boolean; onClear: () => void }) {
  return (
    <div class="refs-empty">
      <Show when={props.hasFilters} fallback={<p>No references in the index yet.</p>}>
        <p>No references match the current filters.</p>
        <button class="refs-clear" type="button" onClick={() => props.onClear()}>
          Clear filters
        </button>
      </Show>
    </div>
  );
}
