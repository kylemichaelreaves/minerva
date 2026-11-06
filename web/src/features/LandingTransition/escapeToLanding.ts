// Escape in a settled chat goes back to the landing — but only an Escape
// nothing else wanted.
//
// Every other Escape in the app (popovers, the scope menu, dialogs, sheets,
// `Select`, list navigation) is a window or element listener that claims the
// key with `preventDefault()`, and most mount after the chat does — so they
// run AFTER this listener, and checking `defaultPrevented` here would see
// none of them. The decision waits until the event has finished dispatching.

import { onCleanup, onMount } from "solid-js";
import type { Turn } from "~/utils/uiTypes";

export interface ChatState {
  onLanding: boolean;
  thinking: boolean;
  hydrating: boolean;
  /** Either flight — Begin's or this one's — still running. */
  transitioning: boolean;
  last: Turn | undefined;
}

/** Whether the chat may leave for the landing: not while Minerva is
 *  considering or still streaming a reply (leaving aborts it), not while a
 *  conversation is loading, and not mid-transition either way. */
export function chatIsSettled(s: ChatState): boolean {
  if (s.onLanding || s.thinking || s.hydrating || s.transitioning) return false;
  return !(s.last?.role === "minerva" && s.last.streaming);
}

export function isPlainEscape(e: KeyboardEvent): boolean {
  return (
    e.key === "Escape" &&
    !e.isComposing &&
    !e.repeat &&
    !e.altKey &&
    !e.ctrlKey &&
    !e.metaKey &&
    !e.shiftKey
  );
}

function isEditable(el: Element): boolean {
  return (
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLSelectElement ||
    (el instanceof HTMLElement && el.isContentEditable)
  );
}

/** Whether leaving now would throw away something being typed: a draft in
 *  the chat composer, or any other field with focus (a search box's Escape
 *  is its own). The empty chat composer itself is fine — that is where
 *  focus usually is. */
export function wouldDropInput(doc: Document = document): boolean {
  const composer = doc.querySelector<HTMLTextAreaElement>(".composer .composer-input");
  if (composer && composer.value.trim() !== "") return true;
  const active = doc.activeElement;
  return active !== null && active !== composer && isEditable(active);
}

/** Calls `onEscape` for a plain Escape no other handler claimed. */
export function useUnclaimedEscape(onEscape: () => void): void {
  onMount(() => {
    let pending: ReturnType<typeof setTimeout> | undefined;
    const onKey = (e: KeyboardEvent) => {
      if (!isPlainEscape(e)) return;
      clearTimeout(pending);
      pending = setTimeout(() => {
        pending = undefined;
        if (!e.defaultPrevented) onEscape();
      }, 0);
    };
    window.addEventListener("keydown", onKey);
    onCleanup(() => {
      clearTimeout(pending);
      window.removeEventListener("keydown", onKey);
    });
  });
}
