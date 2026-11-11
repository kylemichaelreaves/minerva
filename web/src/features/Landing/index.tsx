// Landing — the corpus's frontispiece:
//   1. Header — the doors to every other surface (Read / Citations /
//      Network / Concordance, then Observability apart as a utility) and
//      the theme toggle
//   2. Monogram, whose popover carries the Hegel epigraph
//   3. Composer (Chat entry — the primary affordance)
//   4. One line of corpus stats
//
// The doors used to be a 960px four-column grid under the composer, with
// "Request timing" hung beneath it because a fifth cell would not fit, and
// the Atlas timeline below that. The redesign put the doors in the header
// so the composer stands alone, and moved the Atlas to the Network page.
// On a phone the header has no room for five links, so they render under
// the composer instead.
//
// There was a starter-prompts grid between 2 and 3. It offered four
// un-anchored thematic questions — the shape this corpus answers worst,
// since there is no locus to retrieve — and was removed in #258.

import { Show, untrack, type JSX } from "solid-js";
import { createComposer } from "~/utils/composer";
import ComposeField from "~/components/cards/ComposeField";
import KeyHints from "~/components/cards/KeyHints";
import { ThemeToggle } from "~/components/shell/ThemeToggle";
import { useIsMobile } from "~/components/shell/MobileShellContext";
import { classnames } from "~/utils/util";
import type { Phase } from "~/features/LandingTransition/controller";
import type { ReturnPhase } from "~/features/LandingTransition/returnController";
import LandingNav, { type LandingNavProps } from "~/features/Landing/LandingNav";
import Monogram from "~/features/Landing/Monogram";
import StatsLine from "~/features/Landing/StatsLine";
import {
  ARRIVING_CLASS,
  LEAVING_CLASS,
  inFlight,
  createPhaseEndEffect,
} from "~/features/Landing/phases";
import "~/features/Landing/landing.css";

export type { LandingStats } from "~/api/landingApi";

interface LandingProps extends LandingNavProps {
  onSubmit: (text: string) => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
  /** The work-scope pill, rendered in the box's footer (#350). `ChatRoute`
   *  always passes one — "All works" when unscoped, the work's title when a
   *  work was carried out of the Reader — so the landing's footer matches
   *  the chat composer's and the pill rides through the transition in the
   *  box. Optional here so the component renders without it in isolation. */
  scopeChip?: JSX.Element;
  /** Set while the landing → chat transition runs. The landing stays
   *  mounted as a layer over the chat, fading out (landingTransition.css),
   *  and is inert so nothing on it can be clicked or focused meanwhile. */
  leaving?: Phase;
  /** Set while the chat → landing transition (Escape) runs: the inverse —
   *  this landing is mounted as a layer over the leaving chat, its furniture
   *  drifting back into place, inert until it arrives. */
  arriving?: ReturnPhase;
}

const DESKTOP_HINTS = [
  ["↵", "begin"],
  ["⇧ ↵", "new line"],
] as const;

export default function Landing(props: LandingProps) {
  const c = createComposer({
    minPx: 30,
    maxPx: 320,
    onSubmit: (text) => props.onSubmit(text),
    clearOnSend: false,
  });

  const isMobile = useIsMobile();

  const leaving = () => inFlight(LEAVING_CLASS, props.leaving);
  const arriving = () => inFlight(ARRIVING_CLASS, props.arriving);
  // A landing that arrives by the return transition animates its own parts
  // in; the whole-page `.fade-in` would double them — and, kept on, restart
  // the moment `is-arriving` came off.
  const mountedArriving = untrack(arriving);

  // A flight called off ("New conversation" mid-flight) hands back this same
  // Landing — it never unmounted — and its composer keeps the sent text by
  // design (`clearOnSend: false`). Reset it, or Enter would re-send the old
  // question, and take focus back from the chat composer that just left.
  let textarea: HTMLTextAreaElement | undefined;
  const field = {
    ...c,
    setRef: (el: HTMLTextAreaElement) => {
      textarea = el;
      c.setRef(el);
    },
  };
  // Only on a return to the landing (`leaving` cleared). A flight that runs
  // to its end goes to "idle" as this Landing unmounts; it must not pull
  // focus off the chat composer on its way out.
  createPhaseEndEffect(
    () => props.leaving,
    LEAVING_CLASS,
    () => {
      c.setValue("");
      c.autosize();
      textarea?.focus({ preventScroll: true });
    },
  );
  // Arrived by Escape: the keyboard follows, as it does into the chat on
  // Begin. Inert until now, so its own `autofocus` could not take.
  createPhaseEndEffect(
    () => props.arriving,
    ARRIVING_CLASS,
    () => {
      // The chat it replaced may have been scrolled; the layer was
      // pinned where the landing sits at the top, so this is no jump.
      window.scrollTo(0, 0);
      // A microtask on: this effect can run before the `inert` binding
      // above has come off, and an inert textarea refuses focus.
      queueMicrotask(() => textarea?.focus({ preventScroll: true }));
    },
  );

  return (
    <div
      class={classnames(
        "landing",
        !mountedArriving && "fade-in",
        props.leaving && LEAVING_CLASS[props.leaving],
        props.arriving && ARRIVING_CLASS[props.arriving],
      )}
      attr:inert={leaving() || arriving() ? "" : undefined}
      aria-hidden={leaving() || arriving() ? "true" : undefined}
    >
      <header class="landing-header">
        <span class="mark">
          <span class="pi">M</span>inerva
        </span>
        <Show when={!isMobile()}>
          <LandingNav {...props} />
        </Show>
        <Show when={props.onToggleTheme}>
          <ThemeToggle
            theme={props.theme ?? "light"}
            onToggle={() => props.onToggleTheme?.()}
            variant="text"
          />
        </Show>
      </header>
      <div class="landing-center">
        <div class="landing-hero">
          <Monogram />
          <ComposeField
            variant="landing"
            c={field}
            sendLabel="Begin"
            scopeChip={props.scopeChip}
            hint={
              isMobile() ? (
                <span class="landing-mobile-hint">ask about a passage, a work, an author</span>
              ) : (
                <KeyHints hints={DESKTOP_HINTS} />
              )
            }
          />
          <Show when={isMobile()}>
            <LandingNav {...props} />
          </Show>
          <StatsLine />
        </div>
      </div>
    </div>
  );
}
