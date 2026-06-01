// Reusable hover/focus tooltip in the paper-popover style used by
// inline citations. The trigger is whatever the caller passes as
// `children` (a [n] sup, a Greek word, a chip — anything inline); the
// tooltip appears above it on :hover/:focus-within of the wrap.
//
// Styling lives in `styles.css` under the `.hovertip*` classes so the
// citation rendering (`renderMarkdown.tsx`) and the Reader's
// romanization tooltip share one visual treatment.

import { Show, type JSX } from "solid-js";

export interface HoverTipProps {
  /** Optional small-caps eyebrow above the body. Citations use this
   *  for the locator (e.g. "PLATO · REPUBLIC 509D"); the Reader's
   *  word tooltip omits it. */
  label?: string;
  /** Main tooltip content — string or JSX. */
  body: JSX.Element;
  /** Visible inline trigger; receives :hover/:focus to reveal the tip. */
  children: JSX.Element;
}

export function HoverTip(props: HoverTipProps) {
  return (
    <span class="hovertip-wrap">
      {props.children}
      <span class="hovertip" role="tooltip">
        <Show when={props.label}>
          <span class="hovertip-src">{props.label}</span>
        </Show>
        <span class="hovertip-text">{props.body}</span>
      </span>
    </span>
  );
}
