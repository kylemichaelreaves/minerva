import { Show } from "solid-js";
import { MoonIcon, SunIcon } from "~/components/primitives/Icons";
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
        {/* The shared glyphs from `Icons.tsx` — this button used to
            hand-roll its own sun/moon copies, leaving the exported pair
            dead outside Storybook and the same glyph defined twice
            (#200). Sizing and stroke come from
            `.reader .ico-btn svg` either way. */}
        <Show
          when={props.theme === "dark"}
          fallback={<SunIcon aria-hidden="true" />}
        >
          <MoonIcon aria-hidden="true" />
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
            {"\u00a0light"}
          </>
        }
      >
        <span class="moon" aria-hidden="true" />
        {"\u00a0dark"}
      </Show>
    </button>
  );
}
