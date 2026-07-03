import { Show } from "solid-js";
import type { Theme } from "~/utils/types";

export type ThemeToggleVariant = "icon" | "text" | "cog";

export function ThemeToggle(props: {
  theme: Theme;
  onToggle: () => void;
  variant: ThemeToggleVariant;
  class?: string;
}) {
  const label = () =>
    props.theme === "dark" ? "Switch to light theme" : "Switch to dark theme";

  if (props.variant === "icon") {
    return (
      <button
        type="button"
        class={props.class ?? "ico-btn"}
        aria-label={label()}
        title="Toggle theme"
        onClick={() => props.onToggle()}
      >
        <Show
          when={props.theme === "dark"}
          fallback={
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
            </svg>
          }
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
          </svg>
        </Show>
      </button>
    );
  }

  if (props.variant === "cog") {
    return (
      <button
        type="button"
        class={props.class ?? "sidebar-foot-cog"}
        aria-label={label()}
        title="Toggle theme"
        onClick={() => props.onToggle()}
      >
        ⚙
      </button>
    );
  }

  return (
    <button
      type="button"
      class={props.class ?? "landing-theme-toggle"}
      aria-label={label()}
      title="Toggle theme"
      onClick={() => props.onToggle()}
    >
      <Show
        when={props.theme === "dark"}
        fallback={
          <>
            <span class="sun" aria-hidden="true" />
            &nbsp;light
          </>
        }
      >
        <span class="moon" aria-hidden="true" />
        &nbsp;dark
      </Show>
    </button>
  );
}
