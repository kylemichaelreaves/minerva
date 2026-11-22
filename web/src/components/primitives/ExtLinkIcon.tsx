import type { JSX } from "@solidjs/web";

export function ExtLinkIcon(): JSX.Element {
  return (
    <span class="refcard-ext-ico" aria-hidden="true">
      <svg viewBox="0 0 10 10">
        <path d="M3.5 1.5h5v5" />
        <path d="M8.5 1.5l-7 7" />
      </svg>
    </span>
  );
}
