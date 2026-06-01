import type { JSX } from "solid-js";

export function RailDismissFooter(props: {
  meta: JSX.Element;
  onDismiss: () => void;
}) {
  return (
    <div class="surface-foot">
      <span>{props.meta}</span>
      <div style={{ display: "flex", gap: "14px" }}>
        <button type="button" onClick={() => { props.onDismiss(); }}>
          Dismiss
        </button>
      </div>
    </div>
  );
}
