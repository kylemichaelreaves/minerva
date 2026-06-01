// Inline SVG icons. Stroke + size come from CSS (.icon-btn svg).

import type { JSX } from "solid-js";

type IconProps = JSX.SvgSVGAttributes<SVGSVGElement>;

export const SidebarIcon = (props: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" {...props}>
    <rect x="3" y="4" width="18" height="16" rx="1.5" />
    <line x1="9" y1="4" x2="9" y2="20" />
  </svg>
);

export const PlusIcon = (props: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" {...props}>
    <line x1="5" y1="12" x2="19" y2="12" />
    <line x1="12" y1="5" x2="12" y2="19" />
  </svg>
);

export const SunIcon = (props: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" {...props}>
    <circle cx="12" cy="12" r="3.5" />
    <line x1="12" y1="3" x2="12" y2="5.5" />
    <line x1="12" y1="18.5" x2="12" y2="21" />
    <line x1="3" y1="12" x2="5.5" y2="12" />
    <line x1="18.5" y1="12" x2="21" y2="12" />
    <line x1="5.6" y1="5.6" x2="7.4" y2="7.4" />
    <line x1="16.6" y1="16.6" x2="18.4" y2="18.4" />
    <line x1="5.6" y1="18.4" x2="7.4" y2="16.6" />
    <line x1="16.6" y1="7.4" x2="18.4" y2="5.6" />
  </svg>
);

export const MoonIcon = (props: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" {...props}>
    <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
  </svg>
);

export const SendIcon = (props: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" {...props}>
    <line x1="5" y1="12" x2="19" y2="12" />
    <polyline points="13 6 19 12 13 18" />
  </svg>
);

export const TrashIcon = (props: IconProps) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" {...props}>
    <path d="M4 7h16" />
    <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    <path d="M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" />
    <path d="M10 11v6M14 11v6" />
  </svg>
);
