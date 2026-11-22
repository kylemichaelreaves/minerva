// Mobile top-bar: 44px strip with hamburger (left), title (center),
// optional context action (right). Rendered on every non-landing
// mobile route; the landing carries its own header so this component
// stays absent there.
//
// The component is purely presentational — App.tsx owns the
// drawer-open signal and passes onOpenDrawer + onAction handlers.

import { Show } from "solid-js";
import type { JSX } from "@solidjs/web";

export interface MobileTopBarProps {
  onOpenDrawer: () => void;
  /** Title can be plain text or JSX (so `<em>` italic accents work). */
  title?: JSX.Element;
  /** Optional right-side action — Filters, etc. */
  action?: JSX.Element;
  /** Visible only when the action is interactive — wraps in <button>. */
  onAction?: () => void;
}

export default function MobileTopBar(props: MobileTopBarProps) {
  return (
    <header class="mobile-topbar">
      <button
        type="button"
        class="mobile-topbar-ham"
        aria-label="Open menu"
        onClick={() => props.onOpenDrawer()}
      >
        <span />
      </button>
      <span class="mobile-topbar-title">{props.title}</span>
      <Show when={props.action} fallback={<span class="mobile-topbar-action" aria-hidden="true" />}>
        <Show
          when={props.onAction}
          fallback={<span class="mobile-topbar-action">{props.action}</span>}
        >
          <button type="button" class="mobile-topbar-action" onClick={() => props.onAction?.()}>
            {props.action}
          </button>
        </Show>
      </Show>
    </header>
  );
}
