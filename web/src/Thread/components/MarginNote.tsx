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
  // Narrowed accessors for the `<Show>` callbacks below: a callback body is
  // an owner, not a tracking scope, so the state is read through the
  // accessor `<Show>` hands it, in JSX, rather than off `props` at the top.
  const ready = () => (props.state?.status === "ready" ? props.state : undefined);
  const failed = () => (props.state?.status === "error" ? props.state : undefined);
  const isReady = () => ready() !== undefined;

  return (
    <div
      class={classnames("margin-note", c().pinned && "is-pinned", isExpanded() && "is-expanded")}
    >
      <span class="num">[{c().n}]</span>
      <div class="margin-note-text">
        <Show when={!isReady()}>
          <span>{c().text}</span>
        </Show>
        <Show when={ready()}>
          {(r) => (
            <div class="margin-note-context">
              <Show when={r().context.before.length > 0}>
                <For each={r().context.before}>
                  {(seg) => <p class="ctx ctx-before">{seg.text}</p>}
                </For>
              </Show>
              <p class="ctx ctx-focus">{r().context.focus.text}</p>
              <Show when={r().context.after.length > 0}>
                <For each={r().context.after}>
                  {(seg) => <p class="ctx ctx-after">{seg.text}</p>}
                </For>
              </Show>
            </div>
          )}
        </Show>
      </div>
      <Show when={isLoading()}>
        <span class="margin-note-status">loading more…</span>
      </Show>
      <Show when={failed()}>
        {(err) => (
          <span class="margin-note-status err">couldn't load context: {err().message}</span>
        )}
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
            aria-expanded={isExpanded() ? "true" : "false"}
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
