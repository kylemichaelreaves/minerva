import type { JSX } from "@solidjs/web";

export function smallCapsLabel(letterSpacing: string): JSX.CSSProperties {
  return {
    "font-family": "var(--sans)",
    "font-size": "10.5px",
    "letter-spacing": letterSpacing,
    "text-transform": "uppercase",
    color: "var(--ink-faint)",
  };
}
