import { For, Show } from "solid-js";
import { classnames } from "~/utils/util";
import type { Citation } from "~/utils/types";
import { CiteLocatorLink, PinButton } from "~/Thread/components/CiteControls";
import type { ExpandedStateValue } from "~/Thread/components/MinervaTurnView";

export function MarginNote(props: {
  citation: Citation;
  state: ExpandedStateValue;
  onToggleExpand: () => void;
  onOpenReader: () => void;
  onTogglePin?: (chunkId: string) => void;
  pinnedChunkIds?: string[];
}) {
  const c = () => props.citation;
  const isExpanded = () => Boolean(props.state);
  const isLoading = () => props.state?.status === "loading";
  const isReady = () => props.state?.status === "ready";
  const isError = () => props.state?.status === "error";

  return (
    <div
      class={classnames("margin-note", c().pinned && "is-pinned", isExpanded() && "is-expanded")}
    >
      <span class="num">[{c().n}]</span>
      <div class="margin-note-text">
        <Show when={!isReady()}>
          <span>{c().text}</span>
        </Show>
        <Show when={isReady()}>
          {(_) => {
            const ready = props.state as Extract<ExpandedStateValue, { status: "ready" }>;
            return (
              <div class="margin-note-context">
                <Show when={ready.context.before.length > 0}>
                  <For each={ready.context.before}>
                    {(seg) => <p class="ctx ctx-before">{seg.text}</p>}
                  </For>
                </Show>
                <p class="ctx ctx-focus">{ready.context.focus.text}</p>
                <Show when={ready.context.after.length > 0}>
                  <For each={ready.context.after}>
                    {(seg) => <p class="ctx ctx-after">{seg.text}</p>}
                  </For>
                </Show>
              </div>
            );
          }}
        </Show>
      </div>
      <Show when={isLoading()}>
        <span class="margin-note-status">loading more…</span>
      </Show>
      <Show when={isError()}>
        {(_) => {
          const err = props.state as Extract<ExpandedStateValue, { status: "error" }>;
          return <span class="margin-note-status err">couldn't load context: {err.message}</span>;
        }}
      </Show>
      <span class="src">
        — {c().speaker ? `${c().speaker} · ` : ""}
        <CiteLocatorLink
          citation={c()}
          enabled={true}
          onOpen={() => {
            props.onOpenReader();
          }}
        />
        <Show when={c().chunk_id}>
          <button
            class={classnames("cite-expand", isExpanded() && "is-expanded")}
            type="button"
            onClick={() => {
              props.onToggleExpand();
            }}
            aria-expanded={isExpanded()}
            title={isExpanded() ? "Collapse" : "Show more of the passage"}
          >
            {isExpanded() ? "− less" : "+ more"}
          </button>
        </Show>
        <PinButton
          citation={c()}
          onTogglePin={props.onTogglePin}
          pinnedChunkIds={props.pinnedChunkIds}
        />
      </span>
    </div>
  );
}
