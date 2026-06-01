// Term-card open/close state with URL bidirectionality.
//
// One-way only: URL (?term=<id>) → local resume. We do NOT close the
// card when the URL clears. That asymmetry is deliberate — the open
// click updates the local signal synchronously and the URL via a
// callback that propagates back through props in a later flush. If we
// treated `openTermId === undefined` as "close the card", the brief
// window between click and URL-propagation would clobber the freshly-
// opened card. Closing is owned by the dismiss UI (outside click,
// Esc, close button), which also clears the URL.

import { createEffect, createSignal, type Accessor } from "solid-js";
import { useClickOutside } from "~/hooks/useClickOutside";

export interface OpenTermCard {
  termId: number;
  anchor: DOMRect;
}

export interface TermCardApi {
  openCard: () => OpenTermCard | null;
  /** Toggle: a second click on the same marked term dismisses; a
   *  different term replaces. Updates the URL via the supplied
   *  callback. */
  onTermClick: (termId: number, anchor: DOMRect) => void;
  /** Close + clear the URL param. */
  close: () => void;
}

export interface TermCardProps {
  /** URL state from props.openTermId (mirrored from `?term=`). */
  openTermId: Accessor<number | undefined>;
  /** Push local open-state changes back to the URL. */
  onOpenTermIdChange?: (id: number | null) => void;
}

export function useTermCard(props: TermCardProps): TermCardApi {
  const [openCard, setOpenCard] = createSignal<OpenTermCard | null>(null);

  function onTermClick(termId: number, anchor: DOMRect) {
    if (openCard()?.termId === termId) {
      setOpenCard(null);
      props.onOpenTermIdChange?.(null);
      return;
    }
    setOpenCard({ termId, anchor });
    props.onOpenTermIdChange?.(termId);
  }

  function close() {
    setOpenCard(null);
    props.onOpenTermIdChange?.(null);
  }

  useClickOutside(
    () => document.querySelector(".termcard") as HTMLElement | undefined,
    () => openCard() !== null,
    close,
    {
      event: "mousedown",
      capture: true,
      ignore: (target) =>
        (target as Element).closest(".term-mark") != null,
    },
  );

  // Resume from URL on first paint / reload / deep-link. Sentinel
  // anchor at the viewport top because the URL doesn't (and shouldn't)
  // round-trip pixel coordinates. The tradeoff: pressing the browser
  // back button on an open card leaves it visible until the user
  // dismisses with Esc — acceptable for MVP, since the URL is still
  // the canonical state.
  createEffect(() => {
    const targetId = props.openTermId();
    if (targetId === undefined) return;
    const current = openCard();
    if (current?.termId === targetId) return;
    const w = window.innerWidth;
    const sentinel = new DOMRect(w / 2 - 40, 100, 80, 20);
    setOpenCard({ termId: targetId, anchor: sentinel });
  });

  return { openCard, onTermClick, close };
}
