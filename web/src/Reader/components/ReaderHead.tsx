import { Show } from "solid-js";
import type { WorkRange } from "~/utils/types";

export function ReaderHead(props: { range: WorkRange }) {
  return (
    <div class="head">
      <div class="super">
        {props.range.corpus} · {props.range.lang}
      </div>
      <h1>{props.range.display_title || props.range.work}</h1>
      <Show when={props.range.display_subtitle}>
        <div class="subtitle">{props.range.display_subtitle}</div>
      </Show>
      <div class="byline">{props.range.author}</div>
    </div>
  );
}
