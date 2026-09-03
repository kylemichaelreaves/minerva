import { Show, type JSX } from "solid-js";
import { classnames } from "~/utils/util";

export function SidebarNavRow(props: {
  active: boolean;
  glyph: string;
  title: string;
  titleAttr?: string;
  meta?: string;
  trailing?: JSX.Element;
  onPick: () => void;
  deleteLabel?: string;
  deleteIcon?: JSX.Element;
  onDelete?: () => void;
}) {
  return (
    <div class={classnames("history-item-wrap", props.active && "active")}>
      <button
        class={classnames("history-item", props.active && "active")}
        onClick={() => {
          props.onPick();
        }}
        title={props.titleAttr}
      >
        <span class="history-row">
          <span class="history-glyph">{props.glyph}</span>
          <span class="history-title">{props.title}</span>
          {props.trailing}
        </span>
        <Show when={props.meta}>
          <span class="meta">{props.meta}</span>
        </Show>
      </button>
      <Show when={props.onDelete && props.deleteIcon}>
        <button
          class="history-delete"
          aria-label={props.deleteLabel}
          title={props.deleteLabel}
          onClick={(e) => {
            e.stopPropagation();
            props.onDelete?.();
          }}
        >
          {props.deleteIcon}
        </button>
      </Show>
    </div>
  );
}
