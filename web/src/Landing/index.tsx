// Landing — the corpus's frontispiece. Five elements stacked:
//   1. Π monogram + "Minerva" wordmark + tagline
//   2. Composer (Chat entry — the primary affordance)
//   3. Starter prompts grid (4 questions spanning the corpus)
//   4. Mode entry row — explicit doors to Read / Refs / Network
//   5. Atlas — chronological strip of every author in the corpus

import { For, Show, createSignal, onMount } from "solid-js";
import { fetchLandingStats, type LandingStats } from "~/api/landingApi";
import { createComposer } from "~/utils/composer";
import ComposeField from "~/components/ComposeField";
import { ThemeToggle } from "~/components/ThemeToggle";
import { useMobileShellOptional } from "~/components/MobileShellContext";
import { useMobile } from "~/hooks/useMobile";
import { STARTER_PROMPTS } from "~/data";
import { Atlas } from "~/Landing/components/Atlas";
import "~/Landing/landing.css";

export type { LandingStats } from "~/api/landingApi";

interface LandingProps {
  onSubmit: (text: string) => void;
  onPickPrompt: (text: string) => void;
  onOpenRead: () => void;
  onOpenRefs: (sourceAuthor?: string) => void;
  onOpenNetwork: () => void;
  onOpenConcordance: () => void;
  theme?: "light" | "dark";
  onToggleTheme?: () => void;
}

// Alternate landing logo. The owl-of-Athena is the default mark; on
// ~1-in-5 page loads we instead render the rose-in-the-cross with the
// Hegel/Marx epigraph below it — Hegel's Preface to the Philosophy of
// Right ("Hic Rhodus, hic salta — Hier ist die Rose, hier tanze") that
// Marx picks up in the 18th Brumaire. Random per mount so it reads as
// a quiet Easter egg rather than a feature.
const ROSE_LOGO_PROBABILITY = 0.2;

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

  const [stats, setStats] = createSignal<LandingStats | null>(null);
  onMount(() => {
    void fetchLandingStats()
      .then(setStats)
      .catch(() => {
        // Stats are decorative — silent on failure.
      });
  });

  const fmtNum = (n: number | undefined) => (n === undefined ? "—" : n.toLocaleString());

  return (
    <div class="landing fade-in">
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
            <div class="landing-monogram" tabindex="0">
              <img
                src={useRoseLogo ? "/rose-cross.png" : "/owl.png"}
                alt="Minerva"
                class="landing-monogram-owl"
              />
            </div>
            <div
              class={`landing-monogram-tooltip${useRoseLogo ? " landing-monogram-tooltip-long" : ""}`}
              role="tooltip"
            >
              <Show
                when={useRoseLogo}
                fallback={
                  <>
                    <span class="t1">What is rational is actual,</span>
                    <span class="t2">and what is actual is rational.</span>
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
              </Show>
            </div>
          </div>
          <Show
            when={useRoseLogo}
            fallback={
              <div class="landing-epigraph">
                <span class="landing-epigraph-line">
                  Die Eule der Minerva beginnt erst mit der einbrechenden Dämmerung ihren Flug.
                </span>
                <span class="landing-epigraph-line">
                  The owl of Minerva spreads its wings only with the falling of the dusk.
                </span>
              </div>
            }
          >
            <div class="landing-epigraph">
              <span class="landing-epigraph-line">Hic Rhodus, hic salta.</span>
              <span class="landing-epigraph-line">Hier ist die Rose, hier tanze.</span>
            </div>
          </Show>
          <Show when={false}>
            <div class="landing-word">Minerva</div>
            <div class="landing-tagline">
              A research assistant trained on the canonical works of Western philosophy,
              <br />
              <em>from Homer to Nietzsche.</em>
            </div>
          </Show>

          <ComposeField
            variant="landing"
            c={c}
            sendLabel="Begin"
            hint={
              isMobile() ? (
                <span class="landing-mobile-hint">tap a prompt · or type</span>
              ) : (
                <>
                  <span class="kbd">↵</span> begin&nbsp;&nbsp;
                  <span class="kbd">⇧ ↵</span> new line
                </>
              )
            }
            accessory={
              <div class="landing-pills">
                <For each={STARTER_PROMPTS}>
                  {(p) => (
                    <button
                      class="landing-pill"
                      onClick={() => props.onPickPrompt(p.text)}
                      title={p.text}
                    >
                      <span class="landing-pill-topic">{p.topic}</span>
                      <span class="landing-pill-q">{p.paraphrase}</span>
                    </button>
                  )}
                </For>
              </div>
            }
          />
        </div>

        <div class="landing-modes">
          <button class="landing-mode" onClick={props.onOpenRead}>
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
          <button class="landing-mode" onClick={props.onOpenNetwork}>
            <span class="lbl">
              See the network <span class="arr">→</span>
            </span>
            <span class="sub">visualize the corpus</span>
          </button>
          <button class="landing-mode" onClick={props.onOpenConcordance}>
            <span class="lbl">
              Open concordance <span class="arr">→</span>
            </span>
            <span class="sub">lemma index &middot; KWIC grid</span>
          </button>
        </div>
      </div>

      <Atlas onPickAuthor={(name) => props.onOpenRefs(name)} stats={stats()} isMobile={isMobile} />
    </div>
  );
}
