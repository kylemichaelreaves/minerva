import type { JSX } from "solid-js";

export function smallCapsLabel(letterSpacing: string): JSX.CSSProperties {
  return {
    "font-family": "var(--sans)",
    "font-size": "10.5px",
    "letter-spacing": letterSpacing,
    "text-transform": "uppercase",
    color: "var(--ink-faint)",
  };
}
