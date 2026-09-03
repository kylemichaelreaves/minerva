import { Show, createMemo } from "solid-js";

export function SourceWithHighlight(props: {
  text: string;
  start: number | null;
  end: number | null;
}) {
  // Compute validity reactively. Reading props in the component body
  // (as a plain `if`) evaluates only once; when this instance is reused
  // across curator navigation — e.g. advancing to a row whose span is
  // null — the stale branch would linger and slice(null, null) would
  // wrap the whole passage in a <mark> (issue #61).
  const valid = createMemo(
    () =>
      props.start !== null &&
      props.end !== null &&
      props.start >= 0 &&
      props.end > props.start &&
      props.end <= props.text.length,
  );

  return (
    <Show when={valid()} fallback={<span>{props.text}</span>}>
      <span>{props.text.slice(0, props.start!)}</span>
      <mark class="review-hit">{props.text.slice(props.start!, props.end!)}</mark>
      <span>{props.text.slice(props.end!)}</span>
    </Show>
  );
}
