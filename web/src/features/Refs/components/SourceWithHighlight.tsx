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
  // The memo yields the narrowed span itself (or `false`), so the
  // children receive non-null offsets without an assertion.
  const span = createMemo(() => {
    const start = props.start;
    const end = props.end;
    return (
      start !== null &&
      end !== null &&
      start >= 0 &&
      end > start &&
      end <= props.text.length && { start, end }
    );
  });

  return (
    <Show when={span()} fallback={<span>{props.text}</span>}>
      {(s) => (
        <>
          <span>{props.text.slice(0, s().start)}</span>
          <mark class="review-hit">{props.text.slice(s().start, s().end)}</mark>
          <span>{props.text.slice(s().end)}</span>
        </>
      )}
    </Show>
  );
}
