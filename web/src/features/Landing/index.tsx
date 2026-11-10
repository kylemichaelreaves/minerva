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

import { Show, createEffect, createSignal, on, onMount, untrack, type JSX } from "solid-js";
import { fetchLandingStats, type LandingStats } from "~/api/landingApi";
import { createComposer } from "~/utils/composer";
import ComposeField from "~/components/cards/ComposeField";
import { ThemeToggle } from "~/components/shell/ThemeToggle";
import { useMobileShellOptional } from "~/components/shell/MobileShellContext";
import { useMobile } from "~/hooks/useMobile";
import { classnames } from "~/utils/util";
import type { Phase } from "~/features/LandingTransition/controller";
import type { ReturnPhase } from "~/features/LandingTransition/returnController";
import "~/features/Landing/landing.css";

export type { LandingStats } from "~/api/landingApi";

interface LandingProps {
  onSubmit: (text: string) => void;
  onOpenRead: () => void;
  onOpenRefs: (sourceAuthor?: string) => void;
  onOpenNetwork: () => void;
  onOpenConcordance: () => void;
  onOpenMetrics: () => void;
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

// Alternate landing logo. The owl-of-Athena is the default mark; on
// ~1-in-5 page loads we instead render the rose-in-the-cross with the
// Hegel/Marx epigraph below it — Hegel's Preface to the Philosophy of
// Right ("Hic Rhodus, hic salta — Hier ist die Rose, hier tanze") that
// Marx picks up in the 18th Brumaire. Random per mount so it reads as
// a quiet Easter egg rather than a feature.
const ROSE_LOGO_PROBABILITY = 0.2;

// Landing renders once per app, so a module constant is enough to tie the
// monogram to the epigraph it describes.
const TOOLTIP_ID = "landing-monogram-tooltip";

// The last stats any landing fetched. A landing mounted again — New
// conversation, or Escape from a chat — renders with them at once and
// refreshes behind. The stats line is reserved a line's height either way, so
// its arriving late cannot re-centre the column and move the composer box
// after the return transition has measured where to land.
let lastStats: LandingStats | null = null;

export default function Landing(props: LandingProps) {
  const useRoseLogo = Math.random() < ROSE_LOGO_PROBABILITY;
  const c = createComposer({
    minPx: 30,
    maxPx: 320,
    onSubmit: (text) => props.onSubmit(text),
    clearOnSend: false,
  });

  const shell = useMobileShellOptional();
  const fallbackMobile = useMobile();
  const isMobile = () => shell?.isMobile() ?? fallbackMobile();

  const [stats, setStats] = createSignal<LandingStats | null>(lastStats);
  onMount(() => {
    void fetchLandingStats()
      .then((s) => {
        lastStats = s;
        setStats(s);
      })
      .catch(() => {
        // Stats are decorative — silent on failure.
      });
  });

  const leaving = () => props.leaving === "lift" || props.leaving === "fade";
  const arriving = () => props.arriving === "return" || props.arriving === "fade";
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
  createEffect(
    on(
      () => props.leaving,
      (now, was) => {
        if ((was === "lift" || was === "fade") && now === undefined) {
          c.setValue("");
          c.autosize();
          textarea?.focus({ preventScroll: true });
        }
      },
    ),
  );
  // Arrived by Escape: the keyboard follows, as it does into the chat on
  // Begin. Inert until now, so its own `autofocus` could not take.
  createEffect(
    on(
      () => props.arriving,
      (now, was) => {
        if ((was === "return" || was === "fade") && now === undefined) {
          // The chat it replaced may have been scrolled; the layer was
          // pinned where the landing sits at the top, so this is no jump.
          window.scrollTo(0, 0);
          // A microtask on: this effect can run before the `inert` binding
          // above has come off, and an inert textarea refuses focus.
          queueMicrotask(() => textarea?.focus({ preventScroll: true }));
        }
      },
    ),
  );

  const fmtNum = (n: number | undefined) => (n === undefined ? "—" : n.toLocaleString());

  // The doors out of the landing. One list, placed in the header on desktop
  // and under the composer on a phone (see the file comment). Observability
  // watches the server rather than reading the corpus, so it sits after a
  // divider, muted.
  const nav = () => (
    <nav class="landing-nav" aria-label="Explore the corpus">
      <button type="button" class="landing-nav__link" onClick={() => props.onOpenRead()}>
        Read
      </button>
      <button type="button" class="landing-nav__link" onClick={() => props.onOpenRefs()}>
        Citations
      </button>
      <button type="button" class="landing-nav__link" onClick={() => props.onOpenNetwork()}>
        Network
      </button>
      <button type="button" class="landing-nav__link" onClick={() => props.onOpenConcordance()}>
        Concordance
      </button>
      <span class="landing-nav__sep" aria-hidden="true" />
      <button
        type="button"
        class="landing-nav__link landing-nav__link--util"
        onClick={() => props.onOpenMetrics()}
      >
        Observability
      </button>
    </nav>
  );

  return (
    <div
      class={classnames(
        "landing",
        !mountedArriving && "fade-in",
        props.leaving === "lift" && "is-leaving",
        props.leaving === "fade" && "is-fading",
        props.arriving === "return" && "is-arriving",
        props.arriving === "fade" && "is-arriving-fade",
      )}
      attr:inert={leaving() || arriving() ? "" : undefined}
      aria-hidden={leaving() || arriving() ? "true" : undefined}
    >
      <header class="landing-header">
        <span class="mark">
          <span class="pi">M</span>inerva
        </span>
        <Show when={!isMobile()}>{nav()}</Show>
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
          <div class="landing-monogram-wrap">
            {/* A button rather than a `tabindex`-bearing div: the mark is a
                tab stop only so the epigraph beside it can be reached without
                a mouse (`.landing-monogram:focus-visible +
                .landing-monogram-tooltip`, landing.css), and a bare tab stop
                with no role and no name announces nothing. `aria-describedby`
                is what actually reads the epigraph out; before it the
                `role="tooltip"` element was orphaned. */}
            <button type="button" class="landing-monogram" aria-describedby={TOOLTIP_ID}>
              <img
                src={useRoseLogo ? "/rose-cross.png" : "/owl.png"}
                alt="Minerva"
                class="landing-monogram-owl"
              />
            </button>
            <div
              id={TOOLTIP_ID}
              class={`landing-monogram-tooltip${useRoseLogo ? " landing-monogram-tooltip-long" : ""}`}
              role="tooltip"
            >
              <Show
                when={useRoseLogo}
                fallback={
                  <>
                    <span class="t1">What is rational is actual,</span>
                    <span class="t2">and what is actual is rational.</span>
                    <span class="landing-monogram-tooltip-epigraph">
                      <span lang="de">
                        Die Eule der Minerva beginnt erst mit der einbrechenden Dämmerung ihren
                        Flug.
                      </span>
                      <span>
                        The owl of Minerva spreads its wings only with the falling of the dusk.
                      </span>
                    </span>
                  </>
                }
              >
                <span class="t1">
                  To recognize reason as the rose within the cross of the present and thereby
                  delight in the present — this rational insight is the reconciliation with
                  actuality which philosophy grants to those who've received the inner call to
                  comprehend, to preserve their subjective freedom not in a particular and
                  contingent situation, but in what has being in and for itself.
                </span>
                <span class="landing-monogram-tooltip-epigraph">
                  <span lang="la">Hic Rhodus, hic salta.</span>
                  <span lang="de">Hier ist die Rose, hier tanze.</span>
                </span>
              </Show>
            </div>
          </div>
          <ComposeField
            variant="landing"
            c={field}
            sendLabel="Begin"
            scopeChip={props.scopeChip}
            hint={
              isMobile() ? (
                <span class="landing-mobile-hint">ask about a passage, a work, an author</span>
              ) : (
                <>
                  <span>
                    <span class="kbd">↵</span> begin
                  </span>
                  <span>
                    <span class="kbd">⇧ ↵</span> new line
                  </span>
                </>
              )
            }
          />
          <Show when={isMobile()}>{nav()}</Show>
          <p class="landing-stats">
            <span class="num">{stats()?.authors ?? "—"}</span> authors
            <span class="sep">·</span>
            <span class="num">{fmtNum(stats()?.works)}</span> works
            <span class="sep">·</span>
            <span class="num">{fmtNum(stats()?.xrefs)}</span> cross-references
          </p>
        </div>
      </div>
    </div>
  );
}
