import { For } from "solid-js";

/** The composer footer's keyboard hints: each a key cap and what it does. */
export default function KeyHints(props: {
  hints: readonly (readonly [key: string, label: string])[];
}) {
  return (
    <For each={props.hints}>
      {([key, label]) => (
        <span>
          <span class="kbd">{key}</span> {label}
        </span>
      )}
    </For>
  );
}
