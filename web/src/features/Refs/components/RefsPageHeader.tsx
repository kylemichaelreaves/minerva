import { Show, type JSX } from "solid-js";
import { LoadingDots } from "~/components/primitives/LoadingDots";

export function RefsPageHeader(props: {
  title: string;
  meta?: JSX.Element;
  loading?: boolean;
  error?: string | null;
}) {
  return (
    <>
      <div class="refs-head">
        <h1>{props.title}</h1>
        <Show when={props.meta}>
          <div class="refs-meta">{props.meta}</div>
        </Show>
        <Show when={props.loading}>
          <LoadingDots />
        </Show>
      </div>
      <Show when={props.error}>
        <div class="refs-error">{props.error}</div>
      </Show>
    </>
  );
}
