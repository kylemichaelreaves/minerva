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
//
// The dismiss UI lives in `components/PopoverCard.tsx` as of #356 — this hook
// held the outside-click listener until then, and being the only caller that
// held one is why `ReferenceCard` never got the affordance. Its `suspended`
// gate (#352) moved with it, and reads the `suspendedSubtree` context there
// instead of being threaded as a prop.

import { createEffect, createSignal, type Accessor } from "solid-js";

export interface OpenTermCard {
  termId: number;
  anchor: DOMRect;
  direction?: "ltr" | "rtl";
}

export interface TermCardApi {
  openCard: () => OpenTermCard | null;
  /** Toggle: a second click on the same marked term dismisses; a
   *  different term replaces. Updates the URL via the supplied
   *  callback. */
  onTermClick: (termId: number, anchor: DOMRect, direction?: "ltr" | "rtl") => void;
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
  const [openCard, setOpenCardSignal] = createSignal<OpenTermCard | null>(null);
  // A plain mirror of the open card's term id, for the URL effect's apply
  // phase below: it is untracked, and a signal read there would also lag a
  // write made earlier in the same frame.
  let shownTermId: number | null = null;
  const setOpenCard = (card: OpenTermCard | null) => {
    shownTermId = card?.termId ?? null;
    setOpenCardSignal(card);
  };

  function onTermClick(
    termId: number,
    anchor: DOMRect,
    direction?: "ltr" | "rtl",
  ) {
    if (shownTermId === termId) {
      setOpenCard(null);
      props.onOpenTermIdChange?.(null);
      return;
    }
    setOpenCard({ termId, anchor, direction: direction ?? "ltr" });
    props.onOpenTermIdChange?.(termId);
  }

  function close() {
    setOpenCard(null);
    props.onOpenTermIdChange?.(null);
  }

  // Resume from URL on first paint / reload / deep-link. Sentinel
  // anchor at the viewport top because the URL doesn't (and shouldn't)
  // round-trip pixel coordinates. The tradeoff: pressing the browser
  // back button on an open card leaves it visible until the user
  // dismisses with Esc — acceptable for MVP, since the URL is still
  // the canonical state.
  createEffect(() => props.openTermId(), (targetId) => {
    if (targetId === undefined) return;
    // The compute tracks the URL ONLY; the open card is consulted through
    // the plain `shownTermId` mirror. Tracking openCard() too meant that
    // close() — which nulls openCard first and clears the URL second — could
    // re-run this effect between the two writes; it then saw the stale
    // `?term=` and re-opened the just-dismissed card at the sentinel anchor.
    if (shownTermId === targetId) return;
    const w = window.innerWidth;
    const sentinel = new DOMRect(w / 2 - 40, 100, 80, 20);
    setOpenCard({ termId: targetId, anchor: sentinel });
  });

  return { openCard, onTermClick, close };
}
