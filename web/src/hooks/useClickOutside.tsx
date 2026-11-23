import { createEffect } from "solid-js";
import type { Accessor } from "solid-js";

export interface UseClickOutsideOptions {
  event?: "pointerdown" | "mousedown";
  capture?: boolean;
  /** When true, the outside handler is skipped for this target. */
  ignore?: (target: Node) => boolean;
}

export function useClickOutside(
  rootRef: () => HTMLElement | undefined,
  isActive: Accessor<boolean>,
  onOutside: () => void,
  options: UseClickOutsideOptions = {},
): void {
  const eventName = options.event ?? "pointerdown";
  const capture = options.capture ?? true;

  createEffect(isActive, (active) => {
    if (!active) return;

    const onDoc = (e: Event) => {
      const root = rootRef();
      const t = e.target as Node | null;
      if (!t) return;
      if (options.ignore?.(t)) return;
      if (!root) return;
      if (root.contains(t)) return;
      onOutside();
    };

    document.addEventListener(eventName, onDoc, capture);
    return () => {
      document.removeEventListener(eventName, onDoc, capture);
    };
  });
}
