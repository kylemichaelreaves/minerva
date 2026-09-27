import { Show } from "solid-js";
import { classnames } from "~/utils/util";

export function CiteLocatorLink(props: {
  citation: { chunk_id?: string; src: string };
  enabled: boolean;
  onOpen: () => void;
}) {
  return (
    <Show
      when={props.citation.chunk_id && props.enabled}
      fallback={<span>{props.citation.src}</span>}
    >
      <button
        class="cite-locator-link"
        type="button"
        onClick={() => {
          props.onOpen();
        }}
        title="Open in Reader"
      >
        {props.citation.src}
      </button>
    </Show>
  );
}

export function PinButton(props: {
  citation: { chunk_id?: string; pinned?: boolean };
  pinnedChunkIds?: string[];
  onTogglePin?: (chunkId: string) => void;
}) {
  return (
    <Show when={props.onTogglePin && props.citation.chunk_id}>
      {(id) => {
        const isPinned = () =>
          props.citation.pinned === true || (props.pinnedChunkIds ?? []).includes(id());
        return (
          <button
            class={classnames("cite-pin", isPinned() && "is-pinned")}
            onClick={() => props.onTogglePin?.(id())}
            title={isPinned() ? "Unpin" : "Pin to keep this passage in scope"}
            aria-label={isPinned() ? "Unpin" : "Pin"}
          >
            {isPinned() ? "◆" : "◇"}
          </button>
        );
      }}
    </Show>
  );
}
