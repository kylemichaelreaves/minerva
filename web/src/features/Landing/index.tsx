// Landing — the corpus's frontispiece. Four elements stacked:
//   1. Monogram, whose popover carries the Hegel epigraph
//   2. Composer (Chat entry — the primary affordance)
//   3. Mode entry row — explicit doors to Read / Refs / Network
//   4. Atlas — chronological strip of every author in the corpus
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
import { Atlas } from "~/features/Landing/components/Atlas";
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
  /** Optional work-scope chip, rendered above the composer input (#350).
   *
   *  Optional rather than always-on because the *cold* landing — app start,
   *  or "New question" — really is the unscoped global entry point this
   *  screen was designed as. What it could not express before was a landing
   *  arrived at **from a work**, where the scope is known and wanted: the
   *  Reader's back arrow could hand the work to a conversation and this
   *  screen had nowhere to show it, so leaving the Reader dropped it.
   *
   *  `ChatRoute` passes this only when `chatScope()` is set, so the brand
   *  screen stays uncluttered in the common case. */
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
// refreshes behind: the Atlas caption they fill in is a line tall, and its
// arriving late re-centred the column, moving the composer box 8px after the
// return transition had measured where to land.
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
                  {/* Kept on one line deliberately. Split across two, the
                      newline between `&nbsp;&nbsp;` and the next `<span>`
                      collapses to nothing, and whether that was intended is
                      not readable from the source (typescript:S6772). */}
                  <span class="kbd">↵</span> begin&nbsp;&nbsp;<span class="kbd">⇧ ↵</span> new line
                </>
              )
            }
          />
        </div>

        <div class="landing-modes">
          <button class="landing-mode" onClick={() => props.onOpenRead()}>
            <span class="lbl">
              Read the texts <span class="arr">→</span>
            </span>
            <span class="sub">
              <span class="num">{stats()?.authors ?? "—"}</span> authors &middot;{" "}
              <span class="num">{fmtNum(stats()?.works)}</span> works
            </span>
          </button>
          <button class="landing-mode" onClick={() => props.onOpenRefs()}>
            <span class="lbl">
              Browse citations <span class="arr">→</span>
            </span>
            <span class="sub">
              <span class="num">{fmtNum(stats()?.xrefs)}</span> cross-references
            </span>
          </button>
          <button class="landing-mode" onClick={() => props.onOpenNetwork()}>
            <span class="lbl">
              See the network <span class="arr">→</span>
            </span>
            <span class="sub">visualize the corpus</span>
          </button>
          <button class="landing-mode" onClick={() => props.onOpenConcordance()}>
            <span class="lbl">
              Open concordance <span class="arr">→</span>
            </span>
            <span class="sub">lemma index &middot; KWIC grid</span>
          </button>
        </div>

        {/* Deliberately outside `.landing-modes`. That grid is
            `repeat(4, 1fr)` and its own comment notes the width auto-scales
            "so adding/removing a CTA doesn't force the 4th onto its own
            row" — a fifth cell is the case it was built to avoid. This is
            also a different kind of destination: the four above are for
            reading the corpus, this one is for watching the server, so it
            reads as a utility rather than a peer. */}
        <div class="landing-modes-aside">
          <button class="landing-mode-aside" onClick={() => props.onOpenMetrics()}>
            <span class="lbl">
              Request timing <span class="arr">→</span>
            </span>
            <span class="sub">p95 by route &middot; latency over time</span>
          </button>
        </div>
      </div>

      <Atlas onPickAuthor={(name) => props.onOpenRefs(name)} stats={stats()} isMobile={isMobile} />
    </div>
  );
}
