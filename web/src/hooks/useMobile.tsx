// Mobile-breakpoint detection signal. Returns true when the viewport
// is ≤ 768px wide, false otherwise; updates reactively as the window
// resizes (or the device rotates). Used by App.tsx to swap between
// desktop-shell and mobile-shell behavior — chiefly the sidebar
// drawer pattern and the mobile top-bar.

import { createSignal, onCleanup, onMount } from "solid-js";

const MOBILE_QUERY = "(max-width: 768px)";

export function useMobile() {
  const [isMobile, setIsMobile] = createSignal(
    typeof window !== "undefined" && window.matchMedia(MOBILE_QUERY).matches,
  );

  onMount(() => {
    const mq = window.matchMedia(MOBILE_QUERY);
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    onCleanup(() => mq.removeEventListener("change", handler));
  });

  return isMobile;
}
